# Contador de repeticiones con visión artificial

Cuenta repeticiones de ejercicio en tiempo real desde la webcam, usando detección
de pose de MediaPipe. Incluye curl de bíceps, sentadilla, press de hombros y
elevación lateral, seleccionables desde un menú en pantalla.

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
| `1`–`4` | Elegir ejercicio (con el menú abierto) |
| `r` | Reiniciar el contador |
| `d` | Volcar un diagnóstico por consola |
| `q` | Salir |

Mientras el menú está abierto el conteo se pausa, así que no se suman
repeticiones por accidente al elegir.

## Ejercicios

| Ejercicio | Articulación | Cómo pararte |
|-----------|--------------|--------------|
| Curl de bíceps | Codo | **De perfil** |
| Sentadilla | Rodilla | **De perfil**, cuerpo entero |
| Press de hombros | Codo | **De frente** |
| Elevación lateral | Hombro | **De frente** |

**La orientación no es la misma para todos, y es la causa más común de que no
cuente.** El movimiento tiene que verse *a lo ancho* de la imagen, no hacia la
cámara: MediaPipe estima mal la profundidad, así que un movimiento que va y viene
hacia el lente se mide comprimido y el programa no lo reconoce.

El curl y la sentadilla ocurren en el plano lateral del cuerpo, por eso van de
perfil. El press y la elevación ocurren en el plano frontal, por eso van de
frente. El programa te recuerda cuál corresponde en pantalla y en el menú.

La sentadilla además necesita que entres completo en cuadro: hay que alejarse
unos 2–3 metros.

Al cambiar de ejercicio se reinicia el contador y la calibración.

## Para que la medición funcione

- **La luz tiene que venir de adelante.** Con una ventana detrás, la cámara
  expone para la ventana y el cuerpo queda en silueta.
- Ponete en la orientación que indica el ejercicio, con las tres articulaciones
  dentro del cuadro.
- **Hacé la primera repetición completa y lenta**: sirve para calibrar. Hasta que
  el programa mida tu recorrido no cuenta nada, y te lo avisa en pantalla.

Los tres puntos que se miden se dibujan en verde. Si alguno se pone rojo, la
medición no se acepta y aparece un aviso indicando cuál falla.

## Archivos

| Archivo | |
|---------|--|
| `contador_repeticiones.py` | El programa |
| `requirements.txt` | Dependencias con versiones fijadas |
| `docs/DISENO.md` | Cómo funciona por dentro y por qué |
| `docs/CODIGO.md` | El código explicado línea por línea |
| `pose_landmarker_full.task` | Modelo de MediaPipe, se descarga solo |
| `.venv/`, `__pycache__/` | Generados, no se versionan |

## Ajustes

Los parámetros están al inicio de `contador_repeticiones.py`. Los que se suelen
tocar:

| Parámetro | Valor | Qué controla |
|-----------|-------|--------------|
| `EJERCICIO` | `"curl"` | Ejercicio con el que arranca el programa |
| `LADO` | `"auto"` | Lado a medir: `"derecho"`, `"izquierdo"` o `"auto"` |
| `MODELO` | `"full"` | `lite` (rápido) / `full` / `heavy` (preciso) |
| `MEJORAR_CONTRASTE` | `True` | Realce de contraste contra el contraluz |

Cada ejercicio tiene sus propios ajustes en el diccionario `EJERCICIOS`. Para
agregar uno nuevo alcanza con sumar una entrada ahí: no hay que tocar la lógica.

El resto está documentado en [docs/DISENO.md](docs/DISENO.md), y el código explicado en
[docs/CODIGO.md](docs/CODIGO.md).
