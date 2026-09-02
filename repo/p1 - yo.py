import os
import struct 
class Alumno: 
    def __init__(self, codigo, nombre, apellidos, carrera, ciclo, mensualidad):
        self.codigo = codigo
        self.nombre = nombre
        self.apellidos = apellidos
        self.carrera = carrera
        self.ciclo = ciclo
        self.mensualidad = mensualidad
    def __repr__(self):
        return f"Alumno(codigo={self.codigo}, nombre={self.nombre}, apellidos={self.apellidos}, carrera={self.carrera}, ciclo={self.ciclo}, mensualidad={self.mensualidad})"

REGISTRO_FORMAT = "<5s11s20s15sif"
REGISTRO_SIZE = struct.calcsize(REGISTRO_FORMAT)

# (page_size: int, num_pages: int)
FILE_HEADER_FORMAT = "<II"
FILE_HEADER_SIZE = struct.calcsize(FILE_HEADER_FORMAT) # 8 bytes

# free_list_head: es el puntero al primer espacio eliminado
# (total_records: int, active_records: int, free_list_head: int)
PAGE_HEADER_FORMAT = "<IIi"
PAGE_HEADER_SIZE = struct.calcsize(PAGE_HEADER_FORMAT) # 12 bytes

PAGE_SIZE = 512
REGISTROS_POR_PAGINA = (PAGE_SIZE - PAGE_HEADER_SIZE) // REGISTRO_SIZE  
DELETED = b"\xff" * 5

def pageOffset(pagina):
    return FILE_HEADER_SIZE + (pagina * PAGE_SIZE)

def recordOffset(pagina, registro):
    return pageOffset(pagina) + PAGE_HEADER_SIZE + (registro * REGISTRO_SIZE)

def packRecord(alumno):
    return struct.pack(REGISTRO_FORMAT, 
                       alumno.codigo.encode('utf-8'), 
                       alumno.nombre.encode('utf-8'), 
                       alumno.apellidos.encode('utf-8'), 
                       alumno.carrera.encode('utf-8'), 
                       alumno.ciclo, 
                       alumno.mensualidad)

def decodeString(byte_string):
    return byte_string.split(b'\x00', 1)[0].decode('utf-8')

def unpackRecord(data):
     codigo, nombre, apellidos, carrera, ciclo, mensualidad = struct.unpack(REGISTRO_FORMAT, data)
     return Alumno(
        decodeString(codigo),
        decodeString(nombre),
        decodeString(apellidos),
        decodeString(carrera),
        ciclo,
        mensualidad
    )

class FixedRecord:
    def __init__(self, filename, mode):
        if mode not in ["MOVE_THE_LAST", "FREE_LIST"]:
            raise ValueError("Invalid mode. Use 'MOVE_THE_LAST' or 'FREE_LIST'.")
        self.filename = filename
        self.mode = mode
        if not os.path.exists(filename):
            self.createFile()

    def createFile(self):
        with open(self.filename, "wb") as file:
            file.write(struct.pack(FILE_HEADER_FORMAT, PAGE_SIZE, 0))  

    def readFileHeader(self):
        with open(self.filename, "rb") as file:
            data = file.read(FILE_HEADER_SIZE)
            page_size, num_pages = struct.unpack(FILE_HEADER_FORMAT, data)
            return page_size, num_pages
        
    def writeFileHeader(self, page_size, num_pages):
        with open(self.filename, "r+b") as file:
            file.seek(0)
            file.write(struct.pack(FILE_HEADER_FORMAT, page_size, num_pages))

    def createPage(self): 
        page_size, num_pages = self.readFileHeader()
        page_id = num_pages
        page_header = struct.pack(PAGE_HEADER_FORMAT, 0, 0, -1)
        space_empty = b'\x00' * (PAGE_SIZE - PAGE_HEADER_SIZE)
        with open(self.filename, "r+b") as file:
            file.seek(pageOffset(page_id))
            file.write(page_header + space_empty)
        self.writeFileHeader(page_size, num_pages + 1)
        return page_id

    def readPageHeader(self, page_id):
        with open(self.filename, "rb") as file:
            file.seek(pageOffset(page_id))
            data = file.read(PAGE_HEADER_SIZE)
            return struct.unpack(PAGE_HEADER_FORMAT, data)

    def writePageHeader(self, page_id, total_records, active_records, free_list_head):
        with open(self.filename, "r+b") as file:
            file.seek(pageOffset(page_id))
            file.write(struct.pack(PAGE_HEADER_FORMAT, total_records, active_records, free_list_head))

    def findPageWithSpace(self):
        page_size, num_pages = self.readFileHeader()
        for page in range(num_pages):
            total_records, active_records, free_list_head = self.readPageHeader(page)
            if (self.mode == "FREE_LIST" and free_list_head != -1): 
                return page
            if total_records < REGISTROS_POR_PAGINA:
                return page
        return -1
    
    def add(self, record): 
        page_id = self.findPageWithSpace()
        if page_id == -1:
            page_id = self.createPage()
        total_records, active_records, free_list_head = self.readPageHeader(page_id)
        if (self.mode == "FREE_LIST" and free_list_head != -1):
            slot_id = free_list_head
            next_free = self.readNextFree(page_id, slot_id)
            free_list_head = next_free
        else:
            slot_id = total_records
            total_records += 1
        data = packRecord(record)
        record_offset = recordOffset(page_id, slot_id) 
        with open(self.filename, "r+b") as file:
            file.seek(record_offset)
            file.write(data)
        active_records += 1
        self.writePageHeader(page_id, total_records, active_records, free_list_head)
        return (page_id, slot_id)
    
    def readRecord(self, rid):
        page_id, slot_id = rid
        page_size, num_pages = self.readFileHeader()
        if page_id >= num_pages or page_id < 0:
            return None
        total_records, active_records, free_list_head = self.readPageHeader(page_id)
        if slot_id < 0 or slot_id >= total_records:
            return None
        if self.mode == "FREE_LIST" and self.isRecordDeleted(page_id, slot_id):
            return None
        record_offset = recordOffset(page_id, slot_id)
        with open(self.filename, "rb") as file:
            file.seek(record_offset)
            data = file.read(REGISTRO_SIZE)
        if len(data) < REGISTRO_SIZE:
            return None 
        return unpackRecord(data)
    
    def load(self):
        records = []
        page_size, num_pages = self.readFileHeader()
        for page in range(num_pages):
            total_records, active_records, free_list_head = self.readPageHeader(page)
            for slot in range(total_records):
                rid = (page, slot)
                record = self.readRecord(rid)
                if record is not None:
                    records.append(record)
        return records
    
    def remove(self, rid):
        if self.mode == "MOVE_THE_LAST": 
            return self.removeMoveTheLast(rid)
        elif self.mode == "FREE_LIST":
            return self.removeFreeList(rid)
        else: 
            raise ValueError("Invalid mode. Use 'MOVE_THE_LAST' or 'FREE_LIST'.")
        
    def removeMoveTheLast(self, rid):
        page_id, slot_id = rid
        page_size, num_pages = self.readFileHeader()
        if page_id >= num_pages or page_id < 0:
            return False
        total_records, active_records, free_list_head = self.readPageHeader(page_id)
        if slot_id < 0 or slot_id >= total_records:
            return False
        last_slot_id = total_records - 1
        if slot_id != last_slot_id:
            last_record_offset = recordOffset(page_id, last_slot_id)
            delete_offset = recordOffset(page_id, slot_id)
            with open(self.filename, "r+b") as file:
                file.seek(last_record_offset)
                last_record_data = file.read(REGISTRO_SIZE)
                file.seek(delete_offset)
                file.write(last_record_data)
        self.writePageHeader(page_id, total_records - 1, active_records - 1, free_list_head)
        return True
    def isRecordDeleted(self, page_id, slot_id):
        record_offset = recordOffset(page_id, slot_id)
        with open(self.filename, "rb") as file:
            file.seek(record_offset)
            data = file.read(5)  
            return data == DELETED
    def writeDeletedRecord(self, page_id, slot_id, next_free):
        record_offset = recordOffset(page_id, slot_id)
        data = DELETED + struct.pack("<i", next_free)
        data += b'\x00' * (REGISTRO_SIZE - len(data))
        with open(self.filename, "r+b") as file:
            file.seek(record_offset)
            file.write(data)
    def readNextFree(self, page_id, slot_id):
        record_offset = recordOffset(page_id, slot_id)
        with open(self.filename, "rb") as file:
            file.seek(record_offset + 5)  
            data = file.read(4) 
            return struct.unpack("<i", data)[0]
    def removeFreeList(self, rid):
        page_id, slot_id = rid
        page_size, num_pages = self.readFileHeader()
        if page_id >= num_pages or page_id < 0:
            return False
        total_records, active_records, free_list_head = self.readPageHeader(page_id)
        if slot_id < 0 or slot_id >= total_records:
            return False
        if self.isRecordDeleted(page_id, slot_id):
            return False
        self.writeDeletedRecord(page_id, slot_id, free_list_head)
        free_list_head = slot_id
        active_records -= 1
        self.writePageHeader(page_id, total_records, active_records, free_list_head)
        return True

# ---------- GENERAMOS LOS REGISTROS (base n=100) ----------

def gen_alumnos(n=100, start=0):
    alumnos = []
    for i in range(n):
        alumno = Alumno(
            nombre="Nombre" + str(i+start),
            apellidos="Apellido" + str(i+start),
            carrera="Carrera" + str(i+start),
            ciclo = (i+start)%10 + 1,
            mensualidad = 1000 + (i+start) * 10,
            codigo="COD" + str(i+start)
        )
        alumnos.append(alumno)
    return alumnos

alumnos = gen_alumnos(100)
archivo = FixedRecord("alumnos.dat", "FREE_LIST")

# ---------- INSERTAMOS LOS REGISTROS ----------

rids = []

for alumno in alumnos:
    rid = archivo.add(alumno)
    rids.append(rid)

# ---------- LEEMOS EL ENCABEZADO DEL ARCHIVO Y DE CADA PÁGINA ----------

# vemos la cantidad de páginas y el tamaño de la página

def getFileHeader(archivo):
    page_size, num_pages = archivo.readFileHeader()
    print(f"File Header: (page_size: {page_size}, num_pages: {num_pages})")
    return page_size, num_pages

page_size, num_pages = getFileHeader(archivo)

# vemos la cantidad de registros, registros activos y el puntero a la free_list

def getPageHeaders(archivo, num_pages):
    for i in range(num_pages):
        total_records, active_records, free_list_head = archivo.readPageHeader(i)
        print(f"Page {i} Header: (total_records: {total_records}, active_records: {active_records}, free_list_head: {free_list_head})")

def countActiveRecords(archivo, num_pages):
    activos = 0
    for i in range(num_pages):
        _, active_records, _ = archivo.readPageHeader(i)
        activos += active_records
    return activos

getPageHeaders(archivo, num_pages)

if num_pages > 1:
    print(f"OK: los 100 registros se distribuyen en varias paginas ({num_pages}).")
else:
    print("ERROR: no se distribuyo en varias paginas.")

# vemos al alumno con rid 42

alumno_42 = archivo.readRecord(rids[42])
print(f"Alumno with rid 42: {alumno_42}")

# ---------- PROBAMOS INSERCION ----------

# creamos algunos  alumno

new_alumnos = gen_alumnos(2, start=100)

# insertamos a los nuevos alumnos en el archivo

rid_nuevo_alumno1 = archivo.add(new_alumnos[0])
rids.append(rid_nuevo_alumno1)

rid_nuevo_alumno2 = archivo.add(new_alumnos[1])
rids.append(rid_nuevo_alumno2)

# ---------- PROBAMOS LECTURA ----------

# vemos a los dos nuevos alumnos

alumno1 = archivo.readRecord(rid_nuevo_alumno1)
print(f"Alumno with rid {rid_nuevo_alumno1}: {alumno1}")

alumno2 = archivo.readRecord(rid_nuevo_alumno2)
print(f"Alumno with rid {rid_nuevo_alumno2}: {alumno2}")

# vemos a los alumnos con rid múltiplo de 2 pero no de 4
for i in range(len(rids)):
    if rids[i][1] % 2 == 0 and rids[i][1] % 4 != 0:
        alumno = archivo.readRecord(rids[i])
        print(f"Alumno with rid {rids[i]}: {alumno}")

# ---------- PROBAMOS ELIMINACION ----------

# eliminamos a los alumnos con rid par

deleted_rids = []

for i in range(len(rids)):
    if rids[i][1] % 2 == 0:
        ok = archivo.remove(rids[i])
        if ok:
            deleted_rids.append(rids[i])
            print(f"Deleted Alumno with rid {rids[i]}")

# vemos las cabeceras de las páginas después de la eliminación

print("\nHeaders despues de remove() en FREE_LIST:")
page_size, num_pages = getFileHeader(archivo)
getPageHeaders(archivo, num_pages)

# intentamos acceder a uno de los alumnos eliminados (por ejemplo, el alumno con rid 2)

alumno_eliminado = archivo.readRecord(deleted_rids[0])
print(f"Alumno with rid {deleted_rids[0]}: {alumno_eliminado}")

# probamos load() y verificamos que solo devuelva activos

cargados = archivo.load()
activos_esperados = countActiveRecords(archivo, num_pages)
print(f"load() devolvio {len(cargados)} registros. Activos esperados: {activos_esperados}")
if len(cargados) == activos_esperados:
    print("OK: load() devuelve solo registros validos.")
else:
    print("ERROR: load() no coincide con los activos de headers.")

# ---------- VERIFICAMOS LA REUTILIZACION DE ESPACIO ----------

# insertamos 10 alumnos nuevos para ver si se reutiliza el espacio de los eliminados

print("\nHeaders antes de reinsercion en FREE_LIST:")
page_size, num_pages = getFileHeader(archivo)
getPageHeaders(archivo, num_pages)

nuevos_alumnos = gen_alumnos(10, start=102)
deleted_rids_set = set(deleted_rids)
reused_count = 0

for i in range(10):
    nuevo_alumno = nuevos_alumnos[i]
    rid_nuevo_alumno = archivo.add(nuevo_alumno)
    rids.append(rid_nuevo_alumno)
    if rid_nuevo_alumno in deleted_rids_set:
        reused_count += 1
        print(f"Reused slot: {rid_nuevo_alumno}")
    else:
        print(f"New Alumno rid (no reutilizado): {rid_nuevo_alumno}")

print(f"Slots reutilizados desde FREE_LIST: {reused_count}")
print("Headers despues de reinsercion en FREE_LIST:")
page_size, num_pages = getFileHeader(archivo)
getPageHeaders(archivo, num_pages)

# ---------- VERIFICAMOS COMPORTAMIENTO DE MOVE THE LAST ----------

archivo2 = FixedRecord("alumnos2.dat", "MOVE_THE_LAST")

rids2 = []

for alumno in alumnos:
    rid = archivo2.add(alumno)
    rids2.append(rid)

# vemos las cabeceras del archivo2

page_size2, num_pages2 = archivo2.readFileHeader()


# vemos las cabeceras de las páginas del arvhico2

getPageHeaders(archivo2, num_pages2)

print("\nHeaders antes de remove() en MOVE_THE_LAST:")
page_size2, num_pages2 = getFileHeader(archivo2)
getPageHeaders(archivo2, num_pages2)

# elegimos un rid que no sea el ultimo de su pagina

page_objetivo = rids2[2][0]
total_before, active_before, free_before = archivo2.readPageHeader(page_objetivo)

slot_eliminar = 2
if slot_eliminar >= total_before - 1:
    slot_eliminar = 0

rid_eliminar = (page_objetivo, slot_eliminar)
rid_ultimo_pagina = (page_objetivo, total_before - 1)

alumno_en_slot = archivo2.readRecord(rid_eliminar)
ultimo_en_pagina = archivo2.readRecord(rid_ultimo_pagina)

print(f"Alumno a eliminar: rid {rid_eliminar} -> {alumno_en_slot}")
print(f"Ultimo alumno de la misma pagina antes de eliminar: rid {rid_ultimo_pagina} -> {ultimo_en_pagina}")

archivo2.remove(rid_eliminar)
print(f"Deleted Alumno with rid {rid_eliminar}")

alumno_movido = archivo2.readRecord(rid_eliminar)
print(f"Alumno ahora en rid {rid_eliminar}: {alumno_movido}")

if alumno_movido is not None and ultimo_en_pagina is not None and alumno_movido.codigo == ultimo_en_pagina.codigo:
    print("OK: se movio el ultimo registro de esa pagina al slot eliminado.")
else:
    print("ERROR: no se movio el registro esperado.")

ultimo_slot_now = archivo2.readRecord(rid_ultimo_pagina)
print(f"Lectura del antiguo ultimo slot {rid_ultimo_pagina}: {ultimo_slot_now}")

total_after, active_after, free_after = archivo2.readPageHeader(page_objetivo)
print(f"Header pagina objetivo antes: total={total_before}, active={active_before}, free={free_before}")
print(f"Header pagina objetivo despues: total={total_after}, active={active_after}, free={free_after}")

# --------- VERFICAMOS LA CREACION DE NUEVAS PAGINAS CUANDO SE LLENAN LAS EXISTENTES ---------

# vemos las cabeceras del archivo2

page_size2, num_pages2 = getFileHeader(archivo2)

print("\nVerificacion de creacion de nuevas paginas (MOVE_THE_LAST)")
_, num_pages_before_growth = archivo2.readFileHeader()
print(f"Paginas antes de crecer: {num_pages_before_growth}")

# insertamos hasta detectar crecimiento real de paginas

pool = gen_alumnos(300, start=111)
insertados = 0
i = 0

while i < len(pool):
    rid_nuevo_alumno = archivo2.add(pool[i])
    rids2.append(rid_nuevo_alumno)
    insertados += 1
    _, num_pages_now = archivo2.readFileHeader()
    if num_pages_now > num_pages_before_growth:
        print(f"OK: se creo nueva pagina despues de {insertados} inserciones.")
        break
    i += 1

if i == len(pool):
    print("ERROR: no se detecto crecimiento de paginas.")

page_size2, num_pages2 = getFileHeader(archivo2)
getPageHeaders(archivo2, num_pages2)

