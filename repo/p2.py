import os
import struct
import random
import string

class Matricula:
    def __init__(self, codigo, ciclo, mensualidad, observaciones):
        self.codigo = codigo
        self.ciclo = ciclo
        self.mensualidad = mensualidad
        self.observaciones = observaciones

    def __repr__(self):
        return f"Matricula(codigo-{self.codigo}, ciclo={self.ciclo}, mensualidad={self.mensualidad}, observaciones={self.observaciones})"


# (page_size: int, num_pages: int)
FILE_HEADER_FORMAT = "<II"
FILE_HEADER_SIZE = struct.calcsize(FILE_HEADER_FORMAT)  # 8 bytes

# (num_slots: int, free_space_pointer: int, free_slot_head: int)
PAGE_HEADER_FORMAT = "<IIi"
PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER_FORMAT) # 12 bytes

# (offset: int, length: int)
SLOT_FORMAT = "<ii"
SLOT_SIZE = struct.calcsize(SLOT_FORMAT)  # 8 bytes

# (len_codigo, len_obs, ciclo, mensualidad)
CAMPOS_FIJOS_FORMAT = "<HHif"
CAMPOS_FIJOS_SIZE = struct.calcsize(CAMPOS_FIJOS_FORMAT)  # 12 bytes

PAGE_SIZE = 512


def page_offset(page_id):
    return FILE_HEADER_SIZE + page_id * PAGE_SIZE

def slot_offset(page_id, slot_id):
    return page_offset(page_id) + PAGE_HEADER_SIZE + slot_id * SLOT_SIZE

def pack_record(matricula):
    codigo_b = matricula.codigo.encode('utf-8')
    obs_b = matricula.observaciones.encode('utf-8')
    formato = CAMPOS_FIJOS_FORMAT + f"{len(codigo_b)}s{len(obs_b)}s"
    return struct.pack(formato,
                       len(codigo_b),
                       len(obs_b),
                       matricula.ciclo,
                       matricula.mensualidad,
                       codigo_b,
                       obs_b)

def unpack_record(data):
    len_codigo, len_obs, ciclo, mensualidad = struct.unpack_from(CAMPOS_FIJOS_FORMAT, data, 0)
    offset = CAMPOS_FIJOS_SIZE
    codigo = struct.unpack_from(f"<{len_codigo}s", data, offset)[0].decode('utf-8')
    offset += len_codigo
    observaciones = struct.unpack_from(f"<{len_obs}s", data, offset)[0].decode('utf-8')
    return Matricula(codigo, ciclo, mensualidad, observaciones)

class VariableRecord:
    def __init__(self, filename):
        self.filename = filename
        if not os.path.exists(filename):
            self.create_file()
    
    def create_file(self):
        with open(self.filename, "wb") as f:
            f.write(struct.pack(FILE_HEADER_FORMAT, PAGE_SIZE, 0))

    def read_file_header(self):
        with open(self.filename, "rb") as f:
            data = f.read(FILE_HEADER_SIZE)
            return struct.unpack(FILE_HEADER_FORMAT, data) # page_size, num_pages

    def write_file_header(self, page_size, num_pages):
        with open(self.filename, "r+b") as f:
            f.seek(0)
            f.write(struct.pack(FILE_HEADER_FORMAT, page_size, num_pages))

    def create_page(self):
        page_size, num_pages = self.read_file_header()
        page_id = num_pages

        # 0 slots, free space desde el final de la page, sin slots eliminados 
        page_header = struct.pack(PAGE_HEADER_FORMAT, 0, PAGE_SIZE, -1)
        empty_space = b'\x00' * (PAGE_SIZE - PAGE_HEADER_SIZE)

        with open(self.filename, "r+b") as f:
            f.seek(page_offset(page_id))
            f.write(page_header + empty_space)

        self.write_file_header(page_size, num_pages + 1)
        return page_id


    def read_page_header(self, page_id):
        with open(self.filename, "rb") as f:
            f.seek(page_offset(page_id))
            data = f.read(PAGE_HEADER_SIZE)
            return struct.unpack(PAGE_HEADER_FORMAT, data)

    def write_page_header(self, page_id, num_slots, free_space_ptr, free_slot_head):
        with open(self.filename, "r+b") as f:
            f.seek(page_offset(page_id))
            f.write(struct.pack(PAGE_HEADER_FORMAT, num_slots, free_space_ptr, free_slot_head))

    def read_slot(self, page_id, slot_id):
        with open(self.filename, "rb") as f:
            f.seek(slot_offset(page_id, slot_id))
            data = f.read(SLOT_SIZE)
            return struct.unpack(SLOT_FORMAT, data)  # offset (o next), length

    def write_slot(self, page_id, slot_id, offset, length):
        with open(self.filename, "r+b") as f:
            f.seek(slot_offset(page_id, slot_id))
            f.write(struct.pack(SLOT_FORMAT, offset, length))
        
    

    def find_page_with_space(self, record_size):
        page_size, num_pages = self.read_file_header()
        for page_id in range(num_pages):
            num_slots, free_space_ptr, free_slots_head = self.read_page_header(page_id)

            if free_slots_head != -1: # hay un slot reusable
                required_space = record_size
            else:
                required_space = record_size + SLOT_SIZE

            end_slots_directory = PAGE_HEADER_SIZE + num_slots * SLOT_SIZE
            free_space = free_space_ptr - end_slots_directory

            if free_space >= required_space:
                return page_id

        return -1

    def add(self, matricula):
        record_data = pack_record(matricula)
        record_size = len(record_data)

        page_id = self.find_page_with_space(record_size)
        if page_id == -1:
            page_id = self.create_page()

        num_slots, free_space_ptr, free_slot_head = self.read_page_header(page_id)

        new_free_space_ptr = free_space_ptr - record_size
        with open(self.filename, "r+b") as f:
            f.seek(page_offset(page_id) + new_free_space_ptr)
            f.write(record_data)

        # se guarda la informacion del registro en el slots directory
        if free_slot_head != -1:
            slot_id = free_slot_head
            next_free, _ = self.read_slot(page_id, slot_id)
            new_free_slot_head = next_free
            new_num_slots = num_slots
        else:
            slot_id = num_slots
            new_free_slot_head = free_slot_head 
            new_num_slots = num_slots + 1

        self.write_slot(page_id, slot_id, new_free_space_ptr, record_size)

        self.write_page_header(page_id, new_num_slots, new_free_space_ptr, new_free_slot_head)

        return (page_id, slot_id)

    def read_record(self, rid):
        page_id, slot_id = rid
        page_size, num_pages = self.read_file_header()

        if page_id < 0 or page_id >= num_pages:
            return None

        num_slots, free_space_ptr, free_slot_head = self.read_page_header(page_id)
        if slot_id < 0 or slot_id >= num_slots:
            return None

        offset, length = self.read_slot(page_id, slot_id)
        if length == -1:
            return None

        with open(self.filename, "rb") as f:
            f.seek(page_offset(page_id) + offset)
            data = f.read(length)

        return unpack_record(data)

    def remove(self, rid):
        page_id, slot_id = rid
        page_size, num_pages = self.read_file_header()

        if page_id < 0 or page_id >= num_pages:
            return False

        num_slots, free_space_ptr, free_slot_head = self.read_page_header(page_id)
        if slot_id < 0 or slot_id >= num_slots:
            return False

        offset, length = self.read_slot(page_id, slot_id)
        if length == -1:
            return False

        # encadena este slot al frente de la free list
        self.write_slot(page_id, slot_id, free_slot_head, -1)
        new_free_slot_head = slot_id

        self.write_page_header(page_id, num_slots, free_space_ptr, new_free_slot_head)
        return True

    def load(self):
        records = []
        page_size, num_pages = self.read_file_header()

        for page_id in range(num_pages):
            num_slots, free_space_ptr, free_slot_head = self.read_page_header(page_id)
            for slot_id in range(num_slots):
                record = self.read_record((page_id, slot_id))
                if record is not None:
                    records.append(record)

        return records

    def compact(self, page_id):
        num_slots, free_space_ptr, free_slot_head = self.read_page_header(page_id)

        with open(self.filename, "rb") as f:
            f.seek(page_offset(page_id))
            page_data = f.read(PAGE_SIZE)

        # recolecta los records activos
        active_records = []
        for slot_id in range(num_slots):
            offset, length = self.read_slot(page_id, slot_id)
            if length == -1:
                continue
            record_bytes = page_data[offset: offset + length]
            active_records.append((slot_id, record_bytes))
        
        # recalcula posiciones nuevas
        new_free_space_ptr = PAGE_SIZE
        escrituras = [] # (offset_nuevo, bytes)
        nuevos_offsets = {} # slot_id -> (offset_nuevo, length)

        for slot_id, record_bytes in active_records:
            new_free_space_ptr -= len(record_bytes)
            escrituras.append((new_free_space_ptr, record_bytes))
            nuevos_offsets[slot_id] = (new_free_space_ptr, len(record_bytes))

        # escribe todo en disco
        with open(self.filename, "r+b") as f:
            for offset, data in escrituras:
                f.seek(page_offset(page_id) + offset)
                f.write(data)

        # actualiza cada slot vivo con su nuevo offset
        for slot_id, (offset, length) in nuevos_offsets.items():
            self.write_slot(page_id, slot_id, offset, length)

        # actualiza el page header con el nuevo límite del espacio libre
        self.write_page_header(page_id, num_slots, new_free_space_ptr, free_slot_head)



# ==================== FUNCIONES AUXILIARES DE PRUEBA ====================

def random_string(min_len, max_len):
    n = random.randint(min_len, max_len)
    return ''.join(random.choices(string.ascii_letters, k=n))

def gen_matriculas(n=100, start=0):
    matriculas = []
    for i in range(n):
        matricula = Matricula(
            codigo="MAT" + str(i + start),
            ciclo=(i + start) % 10 + 1,
            mensualidad=1000 + (i + start) * 10,
            observaciones=random_string(0, 60)  # tamaño variable, incluye vacio
        )
        matriculas.append(matricula)
    return matriculas

def get_file_header(archivo):
    page_size, num_pages = archivo.read_file_header()
    print(f"File Header: (page_size: {page_size}, num_pages: {num_pages})")
    return page_size, num_pages

def get_page_headers(archivo, num_pages):
    for i in range(num_pages):
        num_slots, free_space_ptr, free_slot_head = archivo.read_page_header(i)
        print(f"Page {i} Header: (num_slots: {num_slots}, free_space_ptr: {free_space_ptr}, free_slot_head: {free_slot_head})")


# ==================== PRUEBAS FUNCIONALES ====================

if __name__ == "__main__":
    if os.path.exists("matriculas.dat"):
        os.remove("matriculas.dat")

    matriculas = gen_matriculas(100)
    archivo = VariableRecord("matriculas.dat")

    # ---------- INSERTAMOS LOS REGISTROS ----------

    rids = []
    for matricula in matriculas:
        rid = archivo.add(matricula)
        rids.append(rid)

    # ---------- LEEMOS ENCABEZADOS ----------

    page_size, num_pages = get_file_header(archivo)
    get_page_headers(archivo, num_pages)

    if num_pages > 1:
        print(f"OK: los 100 registros se distribuyen en varias paginas ({num_pages}).")
    else:
        print("ERROR: no se distribuyo en varias paginas.")

    # vemos la matricula con rid 42
    matricula_42 = archivo.read_record(rids[42])
    print(f"Matricula with rid {rids[42]}: {matricula_42}")

    # ---------- PROBAMOS INSERCION ----------

    new_matriculas = gen_matriculas(2, start=100)
    rid_nuevo1 = archivo.add(new_matriculas[0])
    rids.append(rid_nuevo1)
    rid_nuevo2 = archivo.add(new_matriculas[1])
    rids.append(rid_nuevo2)

    # ---------- PROBAMOS LECTURA POR RID ----------

    matricula1 = archivo.read_record(rid_nuevo1)
    print(f"Matricula with rid {rid_nuevo1}: {matricula1}")
    matricula2 = archivo.read_record(rid_nuevo2)
    print(f"Matricula with rid {rid_nuevo2}: {matricula2}")

    if (matricula1.codigo == new_matriculas[0].codigo and
            matricula1.observaciones == new_matriculas[0].observaciones):
        print("OK: lectura por RID devuelve el registro correcto.")
    else:
        print("ERROR: lectura por RID no coincide.")

    # RIDs invalidos
    if archivo.read_record((0, 9999)) is None and archivo.read_record((9999, 0)) is None:
        print("OK: RIDs invalidos devuelven None.")
    else:
        print("ERROR: RID invalido no devolvio None.")

    # ---------- PROBAMOS ELIMINACION LOGICA ----------

    print("\nHeaders antes de remove():")
    page_size, num_pages = get_file_header(archivo)
    get_page_headers(archivo, num_pages)    

    deleted_rids = []
    for rid in rids:
        if rid[0] == 0 and rid[1] < 5:
            ok = archivo.remove(rid)
            if ok:
                deleted_rids.append(rid)
                print(f"Deleted Matricula with rid {rid}")

    print("\nHeaders despues de remove():")
    get_page_headers(archivo, num_pages)

    matricula_eliminada = archivo.read_record(deleted_rids[0])
    print(f"Matricula eliminada with rid {deleted_rids[0]}: {matricula_eliminada}")
    if matricula_eliminada is None:
        print("OK: read_record de un slot eliminado devuelve None.")
    else:
        print("ERROR: se leyo un registro eliminado.")

    if archivo.remove(deleted_rids[0]) is False:
        print("OK: remove de un slot ya eliminado devuelve False.")
    else:
        print("ERROR: remove de un slot muerto no devolvio False.")

    # ---------- LOAD() NO DEBE TRAER ELIMINADOS ----------

    cargados = archivo.load()
    esperados = len(rids) - len(deleted_rids)
    print(f"\nload() devolvio {len(cargados)} registros. Esperados: {esperados}")
    if len(cargados) == esperados:
        print("OK: load() no devuelve registros eliminados.")
    else:
        print("ERROR: load() no coincide con los activos.")

    # ---------- VERIFICAMOS REUTILIZACION DE SLOTS (FREE LIST) ----------

    print("\nHeaders antes de reinsercion:")
    _, _, free_slot_head_antes = archivo.read_page_header(0)
    print(f"free_slot_head de pagina 0 antes: {free_slot_head_antes}")

    nuevas = [Matricula("R" + str(i), 1, 100.0, "") for i in range(5)]
    deleted_set = set(deleted_rids)
    reused = 0
    for nueva in nuevas:
        rid_nuevo = archivo.add(nueva)
        rids.append(rid_nuevo)
        if rid_nuevo in deleted_set:
            reused += 1
            print(f"Reused slot: {rid_nuevo}")
        else:
            print(f"New Matricula rid (no reutilizado): {rid_nuevo}")
    print(f"Slots reutilizados desde FREE_LIST: {reused}")

    if reused > 0:
        print("OK: se reutilizaron slots eliminados.")
    else:
        print("ERROR: no se reutilizo ningun slot.")

    # ---------- VERIFICAMOS EL SLOT DIRECTORY (offsets no se pisan) ----------

    vivos = [rid for rid in rids if rid not in deleted_set]
    offsets_por_pagina = {}
    colision = False
    for rid in vivos:
        page_id, slot_id = rid
        offset, length = archivo.read_slot(page_id, slot_id)
        if length == -1:
            continue
        clave = (page_id, offset)
        if clave in offsets_por_pagina:
            colision = True
            break
        offsets_por_pagina[clave] = slot_id
    if not colision:
        print("OK: no hay dos slots vivos apuntando al mismo offset.")
    else:
        print("ERROR: colision de offsets en el slot directory.")

    # ---------- PROBAMOS COMPACT() ----------

    print("\nEstado de pagina 0 antes de compact():")
    get_page_headers(archivo, 1)
    num_slots_antes, fsp_antes, fsh_antes = archivo.read_page_header(0)

    archivo.compact(0)

    print("Estado de pagina 0 despues de compact():")
    get_page_headers(archivo, 1)
    num_slots_despues, fsp_despues, fsh_despues = archivo.read_page_header(0)

    if fsp_despues >= fsp_antes:
        print(f"OK: compact() recupero espacio (free_space_ptr {fsp_antes} -> {fsp_despues}).")
    else:
        print("ERROR: compact() no recupero espacio.")

    vivos_pagina0 = [rid for rid in vivos if rid[0] == 0]
    todos_legibles = all(archivo.read_record(rid) is not None for rid in vivos_pagina0)
    if todos_legibles:
        print("OK: los registros vivos siguen legibles con el mismo RID tras compact().")
    else:
        print("ERROR: algun registro vivo se perdio tras compact().")


    # ---------- VERIFICAR CREACION DE NUEVAS PAGINAS ----------
    _, num_pages_antes = archivo.read_file_header()
    print(f"\nPaginas antes de forzar crecimiento: {num_pages_antes}")
    for i in range(50):
        archivo.add(Matricula("FILL" + str(i), 1, 100.0, random_string(40, 60)))
    _, num_pages_despues = archivo.read_file_header()
    print(f"Paginas despues: {num_pages_despues}")
    if num_pages_despues > num_pages_antes:
        print("OK: se crearon nuevas paginas al llenarse las existentes.")
    else:
        print("ERROR: no se crearon nuevas paginas.")


    print("\nTodas las pruebas ejecutadas.")
