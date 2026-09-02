import struct
import os
import random


class Matricula:
    # ---- File Header: page_size, num_pages ----
    FORMATO_FILE_HEADER = '<ii'

    # ---- Page Header: numSlots, freeSpacePtr ----
    FORMATO_PAGE_HEADER = '<ii'

    # ---- Slot Directory entry: offset, length ----
    FORMATO_SLOT = '<ii'

    def __init__(self, filename, page_size=512):
        self.filename = filename

        self.tam_file_header = struct.calcsize(self.FORMATO_FILE_HEADER)
        self.tam_page_header = struct.calcsize(self.FORMATO_PAGE_HEADER)
        self.tam_slot = struct.calcsize(self.FORMATO_SLOT)

        if not os.path.exists(self.filename):
            self.page_size = page_size
            self.num_pages = 0
            with open(self.filename, 'wb') as f:
                f.write(struct.pack(self.FORMATO_FILE_HEADER, self.page_size, self.num_pages))
        else:
            self._leer_file_header()

    # ------------------------------------------------------------------
    # Serializacion de un registro (codigo y observaciones son variables:
    # se guarda su longitud seguida de los bytes)
    # ------------------------------------------------------------------
    @staticmethod
    def _serialize(record):
        codigo_bytes = record["codigo"].encode('utf-8')
        obs_bytes = record["observaciones"].encode('utf-8')

        buf = struct.pack('<i', len(codigo_bytes)) + codigo_bytes
        buf += struct.pack('<i', int(record["ciclo"]))
        buf += struct.pack('<d', float(record["mensualidad"]))
        buf += struct.pack('<i', len(obs_bytes)) + obs_bytes
        return buf

    @staticmethod
    def _deserialize(data):
        pos = 0
        (codigo_len,) = struct.unpack_from('<i', data, pos); pos += 4
        codigo = data[pos:pos + codigo_len].decode('utf-8'); pos += codigo_len

        (ciclo,) = struct.unpack_from('<i', data, pos); pos += 4
        (mensualidad,) = struct.unpack_from('<d', data, pos); pos += 8

        (obs_len,) = struct.unpack_from('<i', data, pos); pos += 4
        observaciones = data[pos:pos + obs_len].decode('utf-8'); pos += obs_len

        return {
            "codigo": codigo,
            "ciclo": ciclo,
            "mensualidad": mensualidad,
            "observaciones": observaciones,
        }

    # ------------------------------------------------------------------
    # FILE HEADER
    # ------------------------------------------------------------------
    def _leer_file_header(self):
        with open(self.filename, 'rb') as f:
            f.seek(0)
            self.page_size, self.num_pages = struct.unpack(
                self.FORMATO_FILE_HEADER, f.read(self.tam_file_header)
            )

    def _escribir_file_header(self):
        with open(self.filename, 'r+b') as f:
            f.seek(0)
            f.write(struct.pack(self.FORMATO_FILE_HEADER, self.page_size, self.num_pages))

    def get_file_header(self):
        return {"page_size": self.page_size, "num_pages": self.num_pages}

    # ------------------------------------------------------------------
    # PAGINACION
    # ------------------------------------------------------------------
    def _offset_pagina(self, page_id):
        return self.tam_file_header + page_id * self.page_size

    def _offset_slot(self, page_id, slot_id):
        return self._offset_pagina(page_id) + self.tam_page_header + slot_id * self.tam_slot

    def _leer_page_header(self, page_id):
        with open(self.filename, 'rb') as f:
            f.seek(self._offset_pagina(page_id))
            return struct.unpack(self.FORMATO_PAGE_HEADER, f.read(self.tam_page_header))

    def _escribir_page_header(self, page_id, num_slots, free_space_ptr):
        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_pagina(page_id))
            f.write(struct.pack(self.FORMATO_PAGE_HEADER, num_slots, free_space_ptr))

    def get_page_header(self, page_id):
        return self._leer_page_header(page_id)

    def _leer_slot(self, page_id, slot_id):
        with open(self.filename, 'rb') as f:
            f.seek(self._offset_slot(page_id, slot_id))
            return struct.unpack(self.FORMATO_SLOT, f.read(self.tam_slot))

    def _escribir_slot(self, page_id, slot_id, offset, length):
        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_slot(page_id, slot_id))
            f.write(struct.pack(self.FORMATO_SLOT, offset, length))

    def _espacio_libre(self, num_slots, free_space_ptr):
        usado_por_directorio = self.tam_page_header + num_slots * self.tam_slot
        return free_space_ptr - usado_por_directorio

    def _crear_pagina(self):
        page_id = self.num_pages
        empty_page = struct.pack(self.FORMATO_PAGE_HEADER, 0, self.page_size) + \
            (b'\x00' * (self.page_size - self.tam_page_header))
        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_pagina(page_id))
            f.write(empty_page)
        self.num_pages += 1
        self._escribir_file_header()
        return page_id

    def _buscar_slot_tombstone(self, page_id, num_slots):
        for slot_id in range(num_slots):
            offset, length = self._leer_slot(page_id, slot_id)
            if offset == -1:
                return slot_id
        return -1

    # ------------------------------------------------------------------
    # CRUD (todas las operaciones de acceso usan RID = (page_id, slot_id))
    # ------------------------------------------------------------------
    def add(self, record):
        data = self._serialize(record)
        record_size = len(data)

        # 1. Buscar una pagina existente con espacio suficiente
        for page_id in range(self.num_pages):
            num_slots, free_space_ptr = self._leer_page_header(page_id)
            tombstone_slot = self._buscar_slot_tombstone(page_id, num_slots)
            necesita_slot_nuevo = self.tam_slot if tombstone_slot == -1 else 0

            if self._espacio_libre(num_slots, free_space_ptr) >= record_size + necesita_slot_nuevo:
                return self._insertar_en(page_id, num_slots, free_space_ptr, tombstone_slot, data)

        # 2. Ninguna pagina alcanza: crear una nueva
        page_id = self._crear_pagina()
        num_slots, free_space_ptr = self._leer_page_header(page_id)
        if self._espacio_libre(num_slots, free_space_ptr) < record_size + self.tam_slot:
            raise ValueError("El registro es demasiado grande para una pagina vacia")
        return self._insertar_en(page_id, num_slots, free_space_ptr, -1, data)

    def _insertar_en(self, page_id, num_slots, free_space_ptr, tombstone_slot, data):
        record_size = len(data)
        # Los registros crecen desde el final de la pagina hacia el inicio
        new_offset = free_space_ptr - record_size

        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_pagina(page_id) + new_offset)
            f.write(data)

        if tombstone_slot != -1:
            slot_id = tombstone_slot
        else:
            slot_id = num_slots
            num_slots += 1

        self._escribir_slot(page_id, slot_id, new_offset, record_size)
        self._escribir_page_header(page_id, num_slots, new_offset)

        return (page_id, slot_id)

    def readRecord(self, rid):
        page_id, slot_id = rid
        if page_id < 0 or page_id >= self.num_pages:
            return None

        num_slots, free_space_ptr = self._leer_page_header(page_id)
        if slot_id < 0 or slot_id >= num_slots:
            return None

        offset, length = self._leer_slot(page_id, slot_id)
        if offset == -1:
            return None 

        with open(self.filename, 'rb') as f:
            f.seek(self._offset_pagina(page_id) + offset)
            data = f.read(length)

        return self._deserialize(data)

    def remove(self, rid):
        page_id, slot_id = rid
        if page_id < 0 or page_id >= self.num_pages:
            return False

        num_slots, free_space_ptr = self._leer_page_header(page_id)
        if slot_id < 0 or slot_id >= num_slots:
            return False

        offset, length = self._leer_slot(page_id, slot_id)
        if offset == -1:
            return False  

        self._escribir_slot(page_id, slot_id, -1, length)
        return True

    def load(self):
        registros = []
        for page_id in range(self.num_pages):
            num_slots, _ = self._leer_page_header(page_id)
            for slot_id in range(num_slots):
                registro = self.readRecord((page_id, slot_id))
                if registro is not None:
                    registros.append(registro)
        return registros

    def compact(self, page_id):
        if page_id < 0 or page_id >= self.num_pages:
            return

        num_slots, _ = self._leer_page_header(page_id)

        activos = []
        with open(self.filename, 'rb') as f:
            for slot_id in range(num_slots):
                offset, length = self._leer_slot(page_id, slot_id)
                if offset == -1:
                    continue
                f.seek(self._offset_pagina(page_id) + offset)
                activos.append((slot_id, f.read(length)))

        cursor = self.page_size
        with open(self.filename, 'r+b') as f:
            for slot_id, data in activos:
                cursor -= len(data)
                f.seek(self._offset_pagina(page_id) + cursor)
                f.write(data)
                self._escribir_slot(page_id, slot_id, cursor, len(data))

        self._escribir_page_header(page_id, num_slots, cursor)


# ==========================================================================
# PRUEBAS FUNCIONALES
# ==========================================================================

def separador(titulo):
    print("\n" + "=" * 70)
    print(titulo)
    print("=" * 70)


if __name__ == "__main__":
    archivo_prueba = "matricula_test.bin"
    if os.path.exists(archivo_prueba):
        os.remove(archivo_prueba)

    # Paginas pequenas a proposito para forzar varias paginas con 100+ registros
    db = Matricula(archivo_prueba, page_size=512)

    separador("FILE HEADER INICIAL")
    print(db.get_file_header())

    separador("INSERTANDO REGISTROS")
    letras = "abcdefghijklmnopqrstuvwxyz"
    rids = []
    for i in range(120):
        registro = {
            "codigo": letras[i % 26].upper() * (i % 20 + 1),      # tamano variable
            "ciclo": i % 12,
            "mensualidad": round(100.0 + i * 1.5, 2),
            "observaciones": letras[i % 26] * ((i % 50) + 5),      # tamano variable
        }
        rids.append(db.add(registro))

    print(f"Inserción completa. num_pages ahora: {db.num_pages} "
          f"(se distribuyeron {len(rids)} registros en varias paginas)")
    assert db.num_pages > 1, "Los 120 registros deben distribuirse en más de una pagina"

    print(f"\nEstado Page Header pagina 0 (numSlots, freeSpacePtr): {db.get_page_header(0)}")

    separador("TEST readRecord (O(1) via RID)")
    for i in range(5):
        print(f"RID {rids[i]} -> {db.readRecord(rids[i])}")

    separador("ELIMINANDO (via RID)")
    eliminados = []
    for i in range(0, len(rids), 7):
        if db.remove(rids[i]):
            print(f"Eliminado RID {rids[i]}")
            eliminados.append(rids[i])

    separador("VERIFICANDO ELIMINADOS (load() no debe incluirlos)")
    for rid in eliminados:
        resultado = db.readRecord(rid)
        print(f"RID {rid} -> {'SIGUE VISIBLE (ERROR)' if resultado else 'vacio (correcto)'}")
        assert resultado is None, "Un registro eliminado no debe poder leerse"

    print(f"\nEstado Page Header pagina 0 tras eliminar: {db.get_page_header(0)}")
    print("-> el freeSpacePtr no retrocede: el espacio del registro eliminado queda")
    print("   fragmentado dentro de la pagina hasta ejecutar compact().")

    separador("REINSERTANDO")
    nuevos_rids = []
    for i in range(200, 220):
        registro = {
            "codigo": "RE" + "X" * (i % 10 + 1),
            "ciclo": i,
            "mensualidad": 999.9,
            "observaciones": "Z" * ((i % 30) + 10),
        }
        nuevos_rids.append(db.add(registro))
    print(f"Reinserción completa ({len(nuevos_rids)} registros nuevos)")

    separador("load()")
    registros = db.load()
    print(f"Total de registros cargados (activos): {len(registros)}")
    for r in registros[:5]:
        print(" ", r)

    separador("TEST CONSISTENCIA")
    esperado = len(rids) + len(nuevos_rids) - len(eliminados)
    print(f"Esperado: {esperado} | load(): {len(registros)}")
    assert len(registros) == esperado
    print("OK: load() coincide con (insertados - eliminados)")

    separador("TEST FRAGMENTACION Y compact()")
    antes = db.get_page_header(0)
    print(f"Pagina 0 antes de compact -> numSlots/freeSpacePtr: {antes}")
    db.compact(0)
    despues = db.get_page_header(0)
    print(f"Pagina 0 despues de compact -> numSlots/freeSpacePtr: {despues}")
    assert despues[1] >= antes[1], "compact() debe liberar espacio (freeSpacePtr sube o igual)"
    print("OK: compact() libero espacio fragmentado")

    registros_post_compact = db.load()
    print(f"load() tras compact(): {len(registros_post_compact)} registros activos")
    assert len(registros_post_compact) == len(registros)
    print("OK: compact() preservo todos los registros activos")

    separador("VERIFICANDO CREACION DE NUEVA PAGINA CUANDO NO HAY ESPACIO")
    paginas_antes = db.num_pages
    for i in range(300, 320):
        registro = {
            "codigo": f"OV{i}", "ciclo": 1, "mensualidad": 1000.0,
            "observaciones": "overflow_test_" * 3,
        }
        db.add(registro)
    print(f"Paginas antes: {paginas_antes} -> Paginas despues: {db.num_pages}")
    assert db.num_pages > paginas_antes
    print("OK: se crearón paginas nuevas automaticamente cuando ninguna alcanzaba.")

    print("\nFIN DEL TEST")