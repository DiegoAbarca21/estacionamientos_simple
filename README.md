# Gestión de Estacionamientos Particulares — Entrega 2 (versión simple)

Prototipo en Python del sistema de la Entrega 1 (HEI ICIF, Universidad San Sebastián).
Usa **solo la biblioteca estándar** de Python (`csv`, `datetime`, `os`, `re`): no hay que instalar nada.

## Cómo ejecutar

```
python main.py
```

Requiere Python 3.8 o superior. La primera vez, el sistema lee el dataset y deja a cada propietario
ofreciendo su estacionamiento en los tramos en que el dataset muestra que siempre está fuera
(próximas 4 semanas, contadas desde esa primera ejecución; si la demo es más adelante, empiecen de cero
el día anterior). Desde ahí, todo lo que se haga queda guardado en los CSV de `datos/`.

**Para empezar de cero:** borrar `liberaciones.csv`, `bloqueos.csv`, `reservas.csv` e `historial.csv`
de la carpeta `datos/` (no borrar el dataset ni `clientes.csv`; si quieren, dejen el crédito en 0).

## Archivos

| Archivo | Contenido |
|---|---|
| `main.py` | Menú de consola por rol (solo pide datos y muestra resultados) |
| `sistema.py` | Clase `Sistema`: reglas de negocio y las seis funcionalidades |
| `modelos.py` | Clases `Estacionamiento` y `Reserva`, y funciones de fechas |
| `datos.py` | Lectura y escritura de los CSV y del dataset |
| `datos/dataset_estacionamientos.csv` | Dataset de la Entrega 1 (convertido de Excel a CSV) |
| `datos/clientes.csv` | Clientes de prueba (C01 a C10) |
| `datos/liberaciones.csv`, `bloqueos.csv` | Disponibilidad declarada por los propietarios |
| `datos/reservas.csv` | Estado actual de cada reserva |
| `datos/historial.csv` | Todos los eventos con fecha y hora (para el dashboard de la Entrega 3) |

El estacionamiento `E07` pertenece al propietario `P07`.

## Las seis funcionalidades

| Rol | Obligatoria | Propia |
|---|---|---|
| Propietario | Liberar / bloquear | Horario semanal recurrente (con sugerencia según el dataset) |
| Cliente | Reservar / cancelar / liberar anticipadamente | Reserva recurrente (todo o nada, 10 % de descuento) |
| Administrador | Asignar / reasignar | Gestionar contingencias (reasignar o compensar con crédito) |

## Guion para la demostración

El sistema usa la **hora real**. Los pasos 6 y 7 necesitan un horario con oferta, así que conviene
presentar un día hábil entre 08:30 y 17:00 (que es cuando, según el dataset, los propietarios están fuera).

1. **Reservar.** `2 → C04 → 2`: mañana de 10:00 a 13:00, elegir la opción 1. Queda PENDIENTE. Anotar el estacionamiento (ej. E01).
2. **Regla del vehículo.** Con C04, reservar mañana de 11:00 a 12:00 → rechazado: el vehículo ya tiene reserva.
3. **Asignar.** `3 → 1 → T`: la reserva pasa a ASIGNADA.
4. **Bloqueo con reserva vigente.** `1 →` el estacionamiento anotado `→ 3`: mañana de 10:00 a 13:00. El sistema avisa que hay una reserva; confirmar con `s`. La reserva queda AFECTADA (el propietario siempre tiene prioridad).
5. **Contingencia.** `3 → 3 → b`: intentar compensar → rechazado porque hay alternativa. Luego `3 → 3 → a`: el sistema la reasigna al estacionamiento de menor riesgo.
6. **Liberar anticipadamente.** `2 → C05 → 2`: hoy, desde el bloque actual (si son 10:20, de 10:00 a 12:00). Luego opción `4` con esa reserva: se cobra solo lo usado.
7. **Cancelación tardía.** Con C05, reservar hoy en una hora más y cancelar (opción `3`): se cobra el 50 %. Una cancelada con 2 h o más de anticipación no cuesta nada.
8. **Horario recurrente.** `1 → E04 → 4`: se muestran los tramos sugeridos. Ofrecer `sab,dom` de 10:00 a 18:00 por dos semanas.
9. **Reserva recurrente.** `2 → C10 → 5`: L-V de 09:00 a 13:00 la próxima semana → 5 reservas con 10 % de descuento en el mismo estacionamiento.
10. **Persistencia e historial.** Salir (`0`) y volver a ejecutar: todo sigue ahí. `3 → 5` muestra los últimos eventos y `datos/historial.csv` se abre en Excel.
