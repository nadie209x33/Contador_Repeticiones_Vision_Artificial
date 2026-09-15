# Contador de repeticiones con visión artificial

Cuenta repeticiones de ejercicio en tiempo real desde la webcam, mediante
detección de pose de MediaPipe. Incluye curl de bíceps, sentadilla, press de
hombros y elevación lateral, seleccionables desde un menú en pantalla.

## Dos versiones

| | Dónde se ejecuta | Propósito |
|---|---|---|
| `contador_repeticiones.py` | Escritorio, con Python | La versión completa |
| `web/` | Navegador, sin instalación | Uso desde dispositivos móviles o distribución mediante un enlace |

Ambas comparten la misma lógica. La versión web se documenta en
[docs/WEB.md](docs/WEB.md), incluido el procedimiento de publicación en
Cloudflare Pages.

## Requisitos

- Python 3.13
- Una webcam
- Conexión a internet la primera vez, para descargar el modelo de pose

## Instalación

```bash
python -m venv .venv
```

```bash
.venv\Scripts\pip install -r requirements.txt
```

## Uso

```bash
.venv\Scripts\python contador_repeticiones.py
```

| Tecla | Acción |
|-------|--------|
| `e` | Abrir o cerrar el menú de ejercicios |
| `1`–`4` | Seleccionar ejercicio (con el menú abierto) |
| `r` | Reiniciar el contador |
| `d` | Volcar un diagnóstico por consola |
| `q` | Salir |

Mientras el menú permanece abierto el conteo se pausa, de modo que no se
registran repeticiones durante la selección.

## Ejercicios

| Ejercicio | Articulación | Posición frente a la cámara |
|-----------|--------------|------------------------------|
| Curl de bíceps | Codo | **De perfil** |
| Sentadilla | Rodilla | **De perfil**, cuerpo entero |
| Press de hombros | Codo | **De frente** |
| Elevación lateral | Hombro | **De frente** |

**La orientación no es la misma para todos los ejercicios, y constituye la causa
más frecuente de fallos en el conteo.** El movimiento debe percibirse a lo ancho
de la imagen, no en dirección a la cámara: MediaPipe estima la profundidad con
escasa precisión, de manera que un desplazamiento hacia el lente se mide
comprimido y el programa no lo reconoce.

El curl y la sentadilla ocurren en el plano lateral del cuerpo, por lo que
requieren una vista de perfil. El press y la elevación ocurren en el plano
frontal, por lo que requieren una vista frontal. El programa indica la
orientación correspondiente en pantalla y en el menú.

La sentadilla exige además que el cuerpo entre completo en el cuadro, lo que
implica una distancia de entre dos y tres metros respecto de la cámara.

Al cambiar de ejercicio se reinician el contador y la calibración.

## Condiciones para una medición correcta

- **La iluminación debe provenir del frente.** Con una ventana detrás, la cámara
  expone para la ventana y el cuerpo queda en silueta.
- Adoptar la orientación que indica el ejercicio, con las tres articulaciones
  dentro del cuadro.
- **Realizar la primera repetición de forma completa y lenta**: sirve para
  calibrar. Hasta que el programa determine el recorrido no contabiliza nada, y
  lo advierte en pantalla.

Los tres puntos que se miden se dibujan en verde. Si alguno se muestra en rojo,
la medición no se acepta y aparece un aviso que indica cuál de ellos falla.

## Archivos

| Archivo | |
|---------|--|
| `contador_repeticiones.py` | El programa |
| `requirements.txt` | Dependencias con versiones fijadas |
| `docs/DISENO.md` | Funcionamiento interno y fundamentos de las decisiones |
| `docs/CODIGO.md` | El código explicado línea por línea |
| `docs/WEB.md` | La versión para navegador y su publicación |
| `test_contador.py` | Pruebas automatizadas (45 casos) |
| `tests/casos_compartidos.json` | Casos que Python y JavaScript deben reproducir igual |
| `web/` | La versión para navegador |
| `pose_landmarker_full.task` | Modelo de MediaPipe, se descarga automáticamente |
| `.venv/`, `__pycache__/` | Generados, no se versionan |

## Pruebas

```bash
.venv\Scripts\python -m unittest -v
```

Cubren la lógica de medición y conteo: cálculo del ángulo, validación
geométrica, calibración automática, rechazo de ruido, selección de lado y
descarga del modelo. No requieren cámara ni dependencias adicionales.

## Ajustes

Los parámetros se encuentran al inicio de `contador_repeticiones.py`. Los de uso
más frecuente:

| Parámetro | Valor | Qué controla |
|-----------|-------|--------------|
| `EJERCICIO` | `"curl"` | Ejercicio con el que se inicia el programa |
| `LADO` | `"auto"` | Lado a medir: `"derecho"`, `"izquierdo"` o `"auto"` |
| `MODELO` | `"full"` | `lite` (rápido) / `full` / `heavy` (preciso) |
| `MEJORAR_CONTRASTE` | `True` | Realce de contraste frente al contraluz |

Cada ejercicio dispone de sus propios ajustes en el diccionario `EJERCICIOS`.
Para incorporar uno nuevo basta con añadir una entrada: no requiere modificar la
lógica.

El resto se documenta en [docs/DISENO.md](docs/DISENO.md), y el código se
explica en [docs/CODIGO.md](docs/CODIGO.md).
