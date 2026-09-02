import struct
from dataclasses import dataclass

PAGE_SIZE = 512

@dataclass
class Alumno:
    codigo: str
    nombre: str
    apellidos: str
    carrera: str
    ciclo: int
    mensualidad: float

class FixedRecord:

    def __init__(self, file_name, elimination_method):
        self.file_name = file_name
        self.elimination_method = elimination_method

        if (elimination_method == "FREE LIST"):
            self.PAGE_HEADER_FORMAT = "iii"
            self.REGISTER_FORMAT = "5s 11s 20s 15s i f i"
        else:
            self.PAGE_HEADER_FORMAT = "ii"
            self.REGISTER_FORMAT = "5s 11s 20s 15s i f"

        self.PAGE_HEADER_SIZE = struct.calcsize(self.PAGE_HEADER_FORMAT)
        self.REGISTER_SIZE = struct.calcsize(self.REGISTER_FORMAT)
        self.FILE_HEADER_FORMAT = "i"
        self.FILE_HEADER_SIZE = struct.calcsize(self.FILE_HEADER_FORMAT)
        self.MAX_REGISTERS_PER_PAGE = (PAGE_SIZE - self.PAGE_HEADER_SIZE) // self.REGISTER_SIZE
        
    def load(self):
        if self.elimination_method == "FREE LIST":
            return self._load_free_list()
        return self._load_move_the_last()
    
    def add(self, record):
        if self.elimination_method == "FREE LIST":
            return self._add_free_list(record)
        return self._add_move_the_last(record)
    
    def read_record(self, rid: tuple[int, int]):
        register = self._get_binary_record(rid) 
        return struct.unpack(self.REGISTER_FORMAT, register)
    
    def remove(self, rid):
        if self.elimination_method == "FREE LIST":
            return self._remove_free_list(rid)
        return self._remove_move_the_last(rid)        

    def _load_move_the_last(self):

        with open(self.file_name, "rb") as ptr_file:

            file_header = ptr_file.read(self.FILE_HEADER_SIZE)
            num_pages, = struct.unpack(self.FILE_HEADER_FORMAT, file_header)

            registers = []

            for num_page in range(num_pages):

                page_header = ptr_file.read(self.PAGE_HEADER_SIZE)
                num_registers, valid_registers = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)

                for num_register in range(valid_registers):

                    register = ptr_file.read(self.REGISTER_SIZE)
                    register_tuple = struct.unpack(self.REGISTER_FORMAT, register)
                    registers.append(register_tuple)

                ptr_file.seek(
                    self.FILE_HEADER_SIZE +
                    (num_page + 1) * PAGE_SIZE
                )

            return registers

    def _load_free_list(self):

        with open(self.file_name, "rb") as ptr_file:

            file_header = ptr_file.read(self.FILE_HEADER_SIZE)
            num_pages, = struct.unpack(self.FILE_HEADER_FORMAT, file_header)

            registers = []

            for num_page in range(num_pages):

                page_header = ptr_file.read(self.PAGE_HEADER_SIZE)
                num_registers, valid_registers, first_free = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)

                for num_register in range(num_registers):

                    register = ptr_file.read(self.REGISTER_SIZE)
                    register_tuple = struct.unpack(self.REGISTER_FORMAT, register)
                    next_del = register_tuple[6]
                    if (next_del == 0):
                        registers.append(register_tuple)

                ptr_file.seek(
                    self.FILE_HEADER_SIZE +
                    (num_page + 1) * PAGE_SIZE
                )

            return registers

    def _create_new_page(self):

        with open(self.file_name, 'r+b') as ptr_file:

            file_header = ptr_file.read(self.FILE_HEADER_SIZE)
            num_pages, = struct.unpack(self.FILE_HEADER_FORMAT, file_header)
            ptr_file.seek(self.FILE_HEADER_SIZE + PAGE_SIZE * num_pages)

            if self.elimination_method == "FREE LIST":
                ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, 0, 0, 0))
            else:
                ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, 0, 0))
            ptr_file.seek(0)
            ptr_file.write(struct.pack(self.FILE_HEADER_FORMAT, num_pages + 1))

            return True

    def _add_move_the_last(self, record):

        with open(self.file_name, 'r+b') as ptr_file:

            file_header = ptr_file.read(self.FILE_HEADER_SIZE)
            num_pages, = struct.unpack(self.FILE_HEADER_FORMAT, file_header)

            if num_pages == 0:
                self._create_new_page()
                num_pages = 1

            for page_id in range(num_pages - 1, -1, -1):

                ptr_file.seek(
                    self.FILE_HEADER_SIZE +
                    PAGE_SIZE * page_id
                )

                page_header = ptr_file.read(self.PAGE_HEADER_SIZE)
                num_registers, valid_registers = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)

                if num_registers < self.MAX_REGISTERS_PER_PAGE:

                    slot_id = num_registers

                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id +
                        self.PAGE_HEADER_SIZE +
                        self.REGISTER_SIZE * slot_id
                    )

                    ptr_file.write(
                        struct.pack(
                            self.REGISTER_FORMAT,
                            record.codigo.encode(),
                            record.nombre.encode(),
                            record.apellidos.encode(),
                            record.carrera.encode(),
                            record.ciclo,
                            record.mensualidad
                        )
                    )

                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id
                    )

                    ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, num_registers + 1, valid_registers + 1))

                    return (page_id, slot_id)

            self._create_new_page()

            page_id = num_pages
            slot_id = 0

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            ptr_file.write(
                struct.pack(
                    self.PAGE_HEADER_FORMAT,
                    1,
                    1
                )
            )

            ptr_file.write(
                struct.pack(
                    self.REGISTER_FORMAT,
                    record.codigo.encode(),
                    record.nombre.encode(),
                    record.apellidos.encode(),
                    record.carrera.encode(),
                    record.ciclo,
                    record.mensualidad
                )
            )

            return (page_id, slot_id)

    def _add_free_list(self, record):

        with open(self.file_name, 'r+b') as ptr_file:

            file_header = ptr_file.read(self.FILE_HEADER_SIZE)
            num_pages, = struct.unpack(self.FILE_HEADER_FORMAT, file_header)

            if num_pages == 0:
                self._create_new_page()
                num_pages = 1

            for page_id in range(num_pages):

                ptr_file.seek(
                    self.FILE_HEADER_SIZE +
                    PAGE_SIZE * page_id
                )

                page_header = ptr_file.read(self.PAGE_HEADER_SIZE)

                num_registers, valid_registers, first_free = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)
                
                if first_free != 0:
                    slot_id = first_free - 1
                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id +
                        self.PAGE_HEADER_SIZE +
                        self.REGISTER_SIZE * slot_id
                    )
                    old_register = ptr_file.read(self.REGISTER_SIZE)
                    old_register = struct.unpack(self.REGISTER_FORMAT, old_register)
                    next_free = old_register[6]

                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id +
                        self.PAGE_HEADER_SIZE +
                        self.REGISTER_SIZE * slot_id
                    )

                    ptr_file.write(
                        struct.pack(
                            self.REGISTER_FORMAT,
                            record.codigo.encode(),
                            record.nombre.encode(),
                            record.apellidos.encode(),
                            record.carrera.encode(),
                            record.ciclo,
                            record.mensualidad,
                            0
                        )
                    )

                    if next_free == -1:
                        next_free = 0

                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id
                    )

                    ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, num_registers, valid_registers + 1, next_free))

                    return (page_id, slot_id)

                if num_registers < self.MAX_REGISTERS_PER_PAGE:
                    slot_id = num_registers
                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id +
                        self.PAGE_HEADER_SIZE +
                        self.REGISTER_SIZE * slot_id
                    )

                    ptr_file.write(
                        struct.pack(
                            self.REGISTER_FORMAT,
                            record.codigo.encode(),
                            record.nombre.encode(),
                            record.apellidos.encode(),
                            record.carrera.encode(),
                            record.ciclo,
                            record.mensualidad,
                            0
                        )
                    )

                    ptr_file.seek(
                        self.FILE_HEADER_SIZE +
                        PAGE_SIZE * page_id
                    )

                    ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, num_registers + 1, valid_registers + 1, first_free))

                    return (page_id, slot_id)

            self._create_new_page()
            page_id = num_pages

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, 1, 1, 0))

            ptr_file.write(
                struct.pack(
                    self.REGISTER_FORMAT,
                    record.codigo.encode(),
                    record.nombre.encode(),
                    record.apellidos.encode(),
                    record.carrera.encode(),
                    record.ciclo,
                    record.mensualidad,
                    0
                )
            )

            return (page_id, 0)

    def _get_binary_record(self, rid: tuple[int, int]):

        page_id, slot_id = rid

        with open(self.file_name, 'rb') as ptr_file:

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id +
                self.PAGE_HEADER_SIZE +
                self.REGISTER_SIZE * slot_id
            )

            register = ptr_file.read(self.REGISTER_SIZE)

            return register

    def _remove_move_the_last(self, rid: tuple[int, int]):

        page_id, slot_id = rid

        with open(self.file_name, 'r+b') as ptr_file:

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            page_header = ptr_file.read(self.PAGE_HEADER_SIZE)
            num_registers, valid_registers = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)

            register = self._get_binary_record((page_id, num_registers - 1))

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id +
                self.PAGE_HEADER_SIZE +
                self.REGISTER_SIZE * slot_id
            )

            ptr_file.write(register)

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, num_registers - 1, valid_registers - 1))

            return True

    def _remove_free_list(self, rid: tuple[int, int]):

        page_id, slot_id = rid

        with open(self.file_name, 'r+b') as ptr_file:

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            page_header = ptr_file.read(self.PAGE_HEADER_SIZE)
            num_registers, valid_registers, first_free = struct.unpack(self.PAGE_HEADER_FORMAT, page_header)

            free_slot = slot_id + 1

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id +
                self.PAGE_HEADER_SIZE +
                self.REGISTER_SIZE * slot_id +
                self.REGISTER_SIZE - 4
            )

            ptr_file.write(struct.pack('i', first_free if first_free != 0 else -1))

            ptr_file.seek(
                self.FILE_HEADER_SIZE +
                PAGE_SIZE * page_id
            )

            ptr_file.write(struct.pack(self.PAGE_HEADER_FORMAT, num_registers, valid_registers - 1, free_slot)) 

            return True



            



            

            


























        





