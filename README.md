# Estructura Heap File

## `record.py`

En este archivo se maneja el empaquetado de los registros, se soportan esquemas con los siguientes tipos:
- int
- string
- float

1. `record_encoder`

**Input**: `values: list` (lista que contiene los datos del registro)

**Output**: `header_bytes + data_bytes` (bytes de la cabecera y los datos del registro)

Se empaquetan los datos y se genera la cabecera del registro. 

**La cabecera:** 
Esta contiene la cantidad de columnas y mapea los offsets.

1. `record_decoder`

**Input**: `record_bytes: bytes` (bytes del registro: cabecera + datos)

**Output**: `values: list` (lista con los datos recuperados en sus tipos originales)

Reconstruye los valores del registro leyendo la cabecera e interpretando el bloque de datos.
