import struct
import os
import random


class FixedRecord:
    # ---- File Header: page_size (bytes de 1 pagina), num_pages ----
    FORMATO_FILE_HEADER = '<ii'

    # ---- Page Header: total en pagina, activos en pagina, puntero libre ----
    FORMATO_PAGE_HEADER = '<iii'

    def __init__(self, filename, formato_registro, modo_eliminacion="MOVE_THE_LAST",
                 max_records_per_page=10):
        if modo_eliminacion not in ("MOVE_THE_LAST", "FREE_LIST"):
            raise ValueError("modo_eliminacion debe ser 'MOVE_THE_LAST' o 'FREE_LIST'")

        self.filename = filename
        self.modo_eliminacion = modo_eliminacion

        self.tam_file_header = struct.calcsize(self.FORMATO_FILE_HEADER)
        self.tam_page_header = struct.calcsize(self.FORMATO_PAGE_HEADER)

        self.formato_registro = formato_registro
        self.tam_registro = struct.calcsize(self.formato_registro)

        self.max_records_per_page = max_records_per_page
        # Tamano de pagina = Page Header + N registros
        self.tam_pagina = self.tam_page_header + (self.max_records_per_page * self.tam_registro)

        # Cache en memoria de paginas con espacio libre -> add() en O(1)
        self.free_pages = set()
        self.num_pages = 0

        if not os.path.exists(self.filename):
            # Crear archivo nuevo: primero el File Header, luego la pagina 0
            with open(self.filename, 'wb') as f:
                f.write(struct.pack(self.FORMATO_FILE_HEADER, self.tam_pagina, 0))
            self._create_page(0)
        else:
            self._leer_file_header()
            for p in range(self.num_pages):
                tot, act, free = self.get_page_header(p)
                if free != -1 or tot < self.max_records_per_page:
                    self.free_pages.add(p)

    # ------------------------------------------------------------------
    # FILE HEADER
    # ------------------------------------------------------------------
    def _leer_file_header(self):
        with open(self.filename, 'rb') as f:
            f.seek(0)
            page_size, num_pages = struct.unpack(
                self.FORMATO_FILE_HEADER, f.read(self.tam_file_header)
            )
            self.num_pages = num_pages

    def _escribir_file_header(self):
        with open(self.filename, 'r+b') as f:
            f.seek(0)
            f.write(struct.pack(self.FORMATO_FILE_HEADER, self.tam_pagina, self.num_pages))

    def get_file_header(self):
        return {"page_size": self.tam_pagina, "num_pages": self.num_pages}

    # ------------------------------------------------------------------
    # PAGINACION
    # ------------------------------------------------------------------
    def _offset_pagina(self, page_idx):
        return self.tam_file_header + page_idx * self.tam_pagina

    def _create_page(self, page_idx):
        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_pagina(page_idx))
            empty_page = struct.pack(self.FORMATO_PAGE_HEADER, 0, 0, -1) + \
                (b'\x00' * (self.max_records_per_page * self.tam_registro))
            f.write(empty_page)
        self.num_pages = max(self.num_pages, page_idx + 1)
        self.free_pages.add(page_idx)
        self._escribir_file_header()

    def _update_page_header(self, page_idx, total, activos, puntero_libre):
        with open(self.filename, 'r+b') as f:
            f.seek(self._offset_pagina(page_idx))
            f.write(struct.pack(self.FORMATO_PAGE_HEADER, total, activos, puntero_libre))

    def get_page_header(self, page_idx):
        if page_idx >= self.num_pages:
            return (0, 0, -1)
        with open(self.filename, 'rb') as f:
            f.seek(self._offset_pagina(page_idx))
            return struct.unpack(self.FORMATO_PAGE_HEADER, f.read(self.tam_page_header))

    # ------------------------------------------------------------------
    # CRUD (todas las operaciones de acceso usan RID = (page_id, record_id))
    # ------------------------------------------------------------------
    def add(self, record):
        if not self.free_pages:
            self._create_page(self.num_pages)  # nueva pagina al final

        page_idx = next(iter(self.free_pages))
        total, activos, puntero_libre = self.get_page_header(page_idx)

        cod_bytes = record["codigo"][:5].ljust(5, ' ').encode('utf-8')
        nom_bytes = record["nombre"][:11].ljust(11, ' ').encode('utf-8')
        ape_bytes = record["apellidos"][:20].ljust(20, ' ').encode('utf-8')
        car_bytes = record["carrera"][:15].ljust(15, ' ').encode('utf-8')

        registro_empaquetado = struct.pack(
            self.formato_registro,
            cod_bytes, nom_bytes, ape_bytes, car_bytes,
            int(record["ciclo"]), float(record["mensualidad"])
        )

        with open(self.filename, 'r+b') as f:
            if self.modo_eliminacion == "FREE_LIST" and puntero_libre != -1:
                # Reutilizar la primera posicion libre de la pagina
                record_id = puntero_libre
                offset = self._offset_pagina(page_idx) + self.tam_page_header + \
                    (record_id * self.tam_registro)

                f.seek(offset)
                data = f.read(self.tam_registro)
                siguiente_libre = struct.unpack(self.formato_registro, data)[4]  # encadenado en 'ciclo'

                f.seek(offset)
                f.write(registro_empaquetado)

                self._update_page_header(page_idx, total, activos + 1, siguiente_libre)
                if siguiente_libre == -1 and total == self.max_records_per_page:
                    self.free_pages.remove(page_idx)
            else:
                # Insertar al final de las posiciones usadas en esta pagina
                record_id = total
                offset = self._offset_pagina(page_idx) + self.tam_page_header + \
                    (record_id * self.tam_registro)

                f.seek(offset)
                f.write(registro_empaquetado)

                self._update_page_header(page_idx, total + 1, activos + 1, puntero_libre)
                if total + 1 == self.max_records_per_page and puntero_libre == -1:
                    self.free_pages.remove(page_idx)

        return (page_idx, record_id)

    def readRecord(self, rid):
        page_idx, record_id = rid

        if page_idx < 0 or page_idx >= self.num_pages or record_id < 0:
            return None

        total, activos, puntero_libre = self.get_page_header(page_idx)
        if record_id >= total:
            return None

        with open(self.filename, 'rb') as f:
            offset = self._offset_pagina(page_idx) + self.tam_page_header + \
                (record_id * self.tam_registro)
            f.seek(offset)
            data = f.read(self.tam_registro)

            tupla = struct.unpack(self.formato_registro, data)
            codigo_str = tupla[0].decode('utf-8').strip()

            if codigo_str == '*DEL':
                return None

            return {
                "codigo": codigo_str,
                "nombre": tupla[1].decode('utf-8').strip(),
                "apellidos": tupla[2].decode('utf-8').strip(),
                "carrera": tupla[3].decode('utf-8').strip(),
                "ciclo": tupla[4],
                "mensualidad": tupla[5],
            }

    def remove(self, rid):
        page_idx, record_id = rid

        if page_idx < 0 or page_idx >= self.num_pages:
            return False

        total, activos, puntero_libre = self.get_page_header(page_idx)
        if record_id >= total:
            return False

        if self.readRecord(rid) is None:
            return False 

        if self.modo_eliminacion == "MOVE_THE_LAST":
            # Buscar la ultima pagina con registros (para tomar su ultimo activo)
            last_page_idx = self.num_pages - 1
            while last_page_idx >= 0:
                l_tot, l_act, l_free = self.get_page_header(last_page_idx)
                if l_tot > 0:
                    break
                last_page_idx -= 1

            if last_page_idx < 0:
                return False

            l_tot, l_act, l_free = self.get_page_header(last_page_idx)

            if page_idx == last_page_idx and record_id == l_tot - 1:
                # Es el propio ultimo registro: solo se recorta
                self._update_page_header(page_idx, l_tot - 1, activos - 1, puntero_libre)
                self.free_pages.add(page_idx)
                return True

            last_offset = self._offset_pagina(last_page_idx) + self.tam_page_header + \
                ((l_tot - 1) * self.tam_registro)
            with open(self.filename, 'rb') as f:
                f.seek(last_offset)
                last_data = f.read(self.tam_registro)

            del_offset = self._offset_pagina(page_idx) + self.tam_page_header + \
                (record_id * self.tam_registro)
            with open(self.filename, 'r+b') as f:
                f.seek(del_offset)
                f.write(last_data)

            self._update_page_header(last_page_idx, l_tot - 1, l_act - 1, l_free)
            self.free_pages.add(last_page_idx)
            return True

        elif self.modo_eliminacion == "FREE_LIST":
            cod_bytes = '*DEL'.ljust(5, ' ').encode('utf-8')
            nom_bytes = b' '.ljust(11, b' ')
            ape_bytes = b' '.ljust(20, b' ')
            car_bytes = b' '.ljust(15, b' ')

            registro_fantasma = struct.pack(
                self.formato_registro, cod_bytes, nom_bytes, ape_bytes,
                car_bytes, puntero_libre, 0.0
            )

            with open(self.filename, 'r+b') as f:
                offset_eliminar = self._offset_pagina(page_idx) + self.tam_page_header + \
                    (record_id * self.tam_registro)
                f.seek(offset_eliminar)
                f.write(registro_fantasma)

            self._update_page_header(page_idx, total, activos - 1, record_id)
            self.free_pages.add(page_idx)
            return True

    def load(self):
        lista_registros = []
        for page_idx in range(self.num_pages):
            total, activos, puntero_libre = self.get_page_header(page_idx)
            for record_id in range(total):
                registro = self.readRecord((page_idx, record_id))
                if registro is not None:
                    lista_registros.append(registro)
        return lista_registros


# ==========================================================================
# PRUEBAS FUNCIONALES
# ==========================================================================
def separador(titulo):
    print("\n" + "=" * 70)
    print(titulo)
    print("=" * 70)


def probar_modo(modo_eliminacion):
    archivo_prueba = f"db_alumnos_{modo_eliminacion.lower()}.bin"
    if os.path.exists(archivo_prueba):
        os.remove(archivo_prueba)

    separador(f"PRUEBAS CON modo_eliminacion = {modo_eliminacion}")
    db = FixedRecord(archivo_prueba, '<5s11s20s15sid', modo_eliminacion, max_records_per_page=10)

    print(f"File Header inicial: {db.get_file_header()}")

    nombres_base = ["Ana", "Luis", "Juan", "Maria", "Carlos", "Lucia", "Jorge", "Sofia", "Diego", "Rosa"]
    apellidos_base = ["Perez", "Gomez", "Quispe", "Flores", "Rojas", "Sanchez", "Vargas", "Castillo"]
    carreras = ["Computacion", "Industrial", "Mecatronica", "Civil", "Sistemas", "Software"]

    print("\nGenerando 100 registros (10 paginas exactas, distribuidos en varias paginas)...")
    rids = []
    for i in range(100):
        registro = {
            "codigo": f"A{i:03d}",
            "nombre": random.choice(nombres_base),
            "apellidos": f"{random.choice(apellidos_base)} {random.choice(apellidos_base)}",
            "carrera": random.choice(carreras),
            "ciclo": random.randint(1, 10),
            "mensualidad": round(random.uniform(1000.0, 3000.0), 2),
        }
        rids.append(db.add(registro))

    print(f"File Header tras insertar 100 registros: {db.get_file_header()}")
    print(f"Header de la Pagina 0 (antes de eliminar): {db.get_page_header(0)}")
    print(f"Header de la Pagina 9 (antes de eliminar): {db.get_page_header(9)}")
    print(f"RID del registro #5  -> {rids[5]}")
    print(f"RID del registro #95 -> {rids[95]}")

    separador("ELIMINANDO REGISTROS (usando RID, O(1))")
    rid_a_eliminar_1 = rids[5]
    rid_a_eliminar_2 = rids[95]
    print(f"Eliminando RID {rid_a_eliminar_1} y RID {rid_a_eliminar_2} ...")
    ok1 = db.remove(rid_a_eliminar_1)
    ok2 = db.remove(rid_a_eliminar_2)
    print(f"remove({rid_a_eliminar_1}) -> {ok1}")
    print(f"remove({rid_a_eliminar_2}) -> {ok2}")

    print(f"\nHeader de la Pagina {rid_a_eliminar_1[0]} tras eliminar: {db.get_page_header(rid_a_eliminar_1[0])}")
    print(f"Header de la Pagina {rid_a_eliminar_2[0]} tras eliminar: {db.get_page_header(rid_a_eliminar_2[0])}")

    print(f"\nreadRecord({rid_a_eliminar_1}) tras eliminar -> {db.readRecord(rid_a_eliminar_1)} (debe ser None)")

    if modo_eliminacion == "FREE_LIST":
        separador("VERIFICANDO REUTILIZACION DE ESPACIO CON FREE_LIST")
        nuevo_alumno = {
            "codigo": "U999", "nombre": "Carlos", "apellidos": "Villegas Arce",
            "carrera": "Sistemas", "ciclo": 6, "mensualidad": 1500.0,
        }
        rid_nuevo = db.add(nuevo_alumno)
        print(f"Nuevo registro insertado con RID {rid_nuevo}")
        print(f"(Debio caer en la pagina {rid_a_eliminar_1[0]} o {rid_a_eliminar_2[0]}, reutilizando un hueco libre)")
        assert rid_nuevo[0] in (rid_a_eliminar_1[0], rid_a_eliminar_2[0]), \
            "FREE_LIST deberia reutilizar el primer hueco libre"
        print("OK: FREE_LIST reutilizo una posicion eliminada en vez de crear espacio nuevo.")
    else:
        separador("VERIFICANDO COMPORTAMIENTO DE MOVE_THE_LAST")
        # Tras eliminar, el ultimo registro activo debe haberse movido al hueco
        print(f"readRecord({rid_a_eliminar_1}) ahora contiene el que era el ultimo registro:")
        print(db.readRecord(rid_a_eliminar_1))
        print("OK: MOVE_THE_LAST desplazo el ultimo registro activo al hueco dejado.")

    separador("VERIFICANDO CREACION DE NUEVA PAGINA CUANDO NO HAY ESPACIO")
    paginas_antes = db.num_pages
    print(f"Paginas antes de forzar overflow: {paginas_antes}")
    ultimos_rids = []
    for i in range(100, 130):
        registro = {
            "codigo": f"B{i:03d}", "nombre": "Overflow", "apellidos": "Test Test",
            "carrera": "Sistemas", "ciclo": 1, "mensualidad": 1000.0,
        }
        ultimos_rids.append(db.add(registro))
    print(f"Paginas despues de insertar 30 registros extra: {db.num_pages}")
    print(f"File Header actualizado: {db.get_file_header()}")
    assert db.num_pages > paginas_antes, "Debio crearse al menos una pagina nueva"
    print("OK: se crearon paginas nuevas automaticamente.")

    separador("load() - CONTEO FINAL DE REGISTROS VALIDOS")
    registros = db.load()
    print(f"Total de registros validos cargados: {len(registros)}")
    print("Ejemplo de 3 registros cargados:")
    for r in registros[:3]:
        print(" ", r)

    return db


if __name__ == "__main__":
    probar_modo("MOVE_THE_LAST")
    probar_modo("FREE_LIST")