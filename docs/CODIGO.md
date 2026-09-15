# El código explicado

Recorrido completo de `contador_repeticiones.py`, con cada línea comentada. El
archivo `.py` no lleva comentarios: todas las explicaciones se encuentran aquí.

Para el *por qué* de las decisiones, ver [DISENO.md](DISENO.md). Al final hay una
sección sobre [cómo leer código desconocido](#cómo-entender-un-código).

---

## Índice

1. [Importaciones](#1-importaciones)
2. [Configuración](#2-configuración)
3. [Tablas de datos](#3-tablas-de-datos)
4. [Carga del modelo](#4-carga-del-modelo)
5. [Filtros](#5-filtros)
6. [Medición](#6-medición)
7. [Máquina de repeticiones](#7-máquina-de-repeticiones)
8. [Dibujo en pantalla](#8-dibujo-en-pantalla)
9. [El bucle principal](#9-el-bucle-principal)
10. [Cómo entender un código](#cómo-entender-un-código)

---

## 1. Importaciones

```python
import os                              # ver si un archivo existe
import time                            # medir el tiempo transcurrido
import urllib.request                  # descargar el modelo de internet
from collections import deque          # lista con tamaño máximo

import cv2                             # OpenCV: cámara, dibujo y ventanas
import mediapipe as mp                 # armar la imagen que espera el modelo
import numpy as np                     # cuentas con vectores
from mediapipe.tasks import python as mp_python          # opciones del modelo
from mediapipe.tasks.python import vision as mp_vision   # el detector de pose
```

**Qué es un `deque`.** Una lista que se autolimita: al llenarse, cada elemento
nuevo expulsa al más viejo.

> Con `deque(maxlen=3)`, al agregar 1, 2, 3 y luego 4, el contenido queda en
> `[2, 3, 4]`: el 1 se descarta solo. Sirve para conservar "los últimos N"
> sin que la memoria crezca.

---

## 2. Configuración

```python
EJERCICIO = "curl"             # con cuál arranca; se cambia con el menú
LADO = "auto"                  # "derecho", "izquierdo" o "auto"
MODELO = "full"                # variante del modelo a descargar
ESPEJO = True                  # invertir la imagen como un espejo
MEJORAR_CONTRASTE = True       # aplicar realce contra el contraluz
```

```python
DURACION_MIN_REP = 0.5         # segundos mínimos entre dos repeticiones
MARGEN_UMBRAL = 0.15           # cuánto del recorrido hay que completar (85%)
RUIDO_MAXIMO = 0.15            # cambio por frame admitido, sobre el recorrido
VENTANA_CALIBRACION = 300      # frames de historial (300 / 30 FPS = 10 segundos)
CALIBRACION_AUTOMATICA = True  # deducir los umbrales del movimiento real
```

```python
UMBRAL_VISIBILIDAD = 0.5       # confianza mínima de los dos puntos externos
TOLERANCIA_LONGITUD = 0.4      # cuánto puede variar el largo del miembro (40%)
FILTRO_CORTE = 1.0             # suavizado con el cuerpo quieto
FILTRO_BETA = 10.0             # cuánto se afloja al moverse rápido
```

```python
TAMANO_MINIMO_MODELO = 1_000_000   # bytes; por debajo, la descarga fallo
RESOLUCION = (1280, 720)           # resolución pedida a la cámara
VENTANA = "Contador de repeticiones"   # título de la ventana
```

Cabe señalar que aquí **no** figuran los umbrales de ángulo ni la amplitud
mínima: dependen del ejercicio y residen en el diccionario `EJERCICIOS`.

---

## 3. Tablas de datos

### Los puntos del cuerpo

```python
PUNTOS = {
    "derecho": {
        "hombro": (12,),                     # un solo landmark
        "codo": (14,),
        "muneca": (16, 18, 20, 22),          # muñeca + meñique + índice + pulgar
        "cadera": (24,),
        "rodilla": (26,),
        "tobillo": (28, 30, 32),             # tobillo + talón + punta del pie
    },
    "izquierdo": {
        "hombro": (11,),
        "codo": (13,),
        "muneca": (15, 17, 19, 21),
        "cadera": (23,),
        "rodilla": (25,),
        "tobillo": (27, 29, 31),
    },
}
```

MediaPipe numera los 33 puntos del cuerpo siempre igual: los impares son del lado
izquierdo y los pares del derecho.

Cada articulación es un **grupo** de landmarks, aunque casi todos tengan uno solo.
La muñeca y el tobillo son grupos de verdad porque son los dos puntos donde
MediaPipe reporta peor la confianza: promediarlos con los dedos o con el pie
rescata la medición cuando el punto principal falla.

### Los ejercicios

```python
EJERCICIOS = {
    "curl": {
        "nombre": "Curl de biceps",          # lo que se muestra en pantalla
        "vista": "de perfil",                # cómo pararse frente a la cámara
        "puntos": ("hombro", "codo", "muneca"),   # el del medio es el vértice
        "contar_en": "up",                   # la rep termina con el ángulo chico
        "amplitud_min": 50,                  # recorrido mínimo para calibrar
        "flexionado": 55,                    # solo si se apaga la calibración
        "extendido": 155,
    },
    "sentadilla": {
        "nombre": "Sentadilla",
        "vista": "de perfil, cuerpo entero",
        "puntos": ("cadera", "rodilla", "tobillo"),
        "contar_en": "up",
        "amplitud_min": 45,
        "flexionado": 80,
        "extendido": 165,
    },
    "press": {
        "nombre": "Press de hombros",
        "vista": "de frente",
        "puntos": ("hombro", "codo", "muneca"),
        "contar_en": "ciclo",                # la rep termina con el ángulo grande
        "amplitud_min": 45,
        "flexionado": 80,
        "extendido": 160,
    },
    "elevacion": {
        "nombre": "Elevacion lateral",
        "vista": "de frente",
        "puntos": ("cadera", "hombro", "codo"),   # el vértice es el hombro
        "contar_en": "ciclo",
        "amplitud_min": 35,                  # recorrido corto: exige menos
        "flexionado": 25,
        "extendido": 80,
    },
}
```

Toda la diferencia entre ejercicios reside aquí. Incorporar uno nuevo requiere
únicamente añadir una entrada: no se modifica ninguna línea de lógica.

La elevación lateral es la más ilustrativa: su vértice es el **hombro**, no el
codo. Eso demuestra que `calcular_angulo` es genérica de verdad.

El campo `vista` existe porque MediaPipe estima mal la profundidad. Un movimiento
que va hacia la cámara cae justo sobre ese eje y se mide comprimido, así que cada
ejercicio tiene su orientación correcta y el programa la muestra en pantalla.

```python
NOMBRES = {
    "hombro": "el hombro",                   # para escribir los avisos
    "codo": "el codo",
    "muneca": "la mano",
    "cadera": "la cadera",
    "rodilla": "la rodilla",
    "tobillo": "el pie",
}
```

Sin esto, el cartel diría "No veo bien: muneca" en vez de "No veo bien la mano".

### El esqueleto

```python
POSE_CONNECTIONS = [
    (11, 12),      # hombro izquierdo - hombro derecho
    (11, 13),      # hombro izq - codo izq
    (13, 15),      # codo izq - muñeca izq
    (12, 14),      # hombro der - codo der
    (14, 16),      # codo der - muñeca der
    (11, 23),      # hombro izq - cadera izq
    (12, 24),      # hombro der - cadera der
    (23, 24),      # cadera izq - cadera der
    (23, 25),      # cadera izq - rodilla izq
    (25, 27),      # rodilla izq - tobillo izq
    (27, 29),      # tobillo izq - talón izq
    (27, 31),      # tobillo izq - punta del pie izq
    (24, 26),      # cadera der - rodilla der
    (26, 28),      # rodilla der - tobillo der
    (28, 30),      # tobillo der - talón der
    (28, 32),      # tobillo der - punta del pie der
    (15, 17),      # muñeca izq - meñique izq
    (15, 19),      # muñeca izq - índice izq
    (15, 21),      # muñeca izq - pulgar izq
    (16, 18),      # muñeca der - meñique der
    (16, 20),      # muñeca der - índice der
    (16, 22),      # muñeca der - pulgar der
]
```

Qué pares de puntos se unen con una línea. Está escrito a mano porque la API
vieja, que traía estas conexiones incluidas, ya no existe.

```python
FUENTE = cv2.FONT_HERSHEY_SIMPLEX      # tipografía del texto en pantalla
CONTORNO = ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, -2), (0, 2), (-2, 0), (2, 0))
```

`CONTORNO` son ocho corrimientos en píxeles: cuatro diagonales y cuatro rectos.
Sirven para dibujar el borde negro alrededor del texto.

---

## 4. Carga del modelo

```python
MODEL_PATH = f"pose_landmarker_{MODELO}.task"    # nombre del archivo local
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    f"pose_landmarker_{MODELO}/float16/latest/pose_landmarker_{MODELO}.task"
)                                                # de dónde bajarlo
```

La `f` antes de las comillas permite meter variables dentro del texto. Con
`MODELO = "full"`, `MODEL_PATH` queda en `pose_landmarker_full.task`.

Los dos textos de `MODEL_URL` se pegan solos: en Python, dos cadenas seguidas
entre paréntesis se concatenan.

```python
def descargar_modelo(destino=MODEL_PATH, url=MODEL_URL):
    parcial = destino + ".parcial"               # nombre temporal
    print("Descargando modelo de pose (solo la primera vez)...")
    try:
        urllib.request.urlretrieve(url, parcial)     # bajar al temporal
        if os.path.getsize(parcial) < TAMANO_MINIMO_MODELO:
            raise OSError("el archivo descargado es demasiado chico")
        os.replace(parcial, destino)             # recién ahora, el nombre real
    except Exception as error:
        if os.path.exists(parcial):
            os.remove(parcial)                   # no dejar restos
        raise RuntimeError(
            f"No se pudo descargar el modelo desde {url}\n  {error}\n"
            "Revisar la conexion a internet y volver a ejecutar."
        ) from error
```

La descarga es **atómica**: el archivo viaja con el nombre `.parcial` y solo
recibe su nombre definitivo si la transferencia termina y supera el tamaño
mínimo.

Sin esa precaución, una descarga interrumpida deja un archivo truncado. A partir
de ahí `os.path.exists()` devuelve `True` en cada ejecución, el programa intenta
cargar un modelo corrupto y falla con un error que no sugiere ni la causa ni la
solución, que sería borrar el archivo a mano.

`os.replace` reemplaza de forma atómica dentro del mismo sistema de archivos: o
está el archivo viejo, o está el nuevo, nunca una mezcla.

```python
def cargar_landmarker():
    if not os.path.exists(MODEL_PATH):           # ¿ya está descargado?
        descargar_modelo()

    opciones = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),  # qué archivo usar
        running_mode=mp_vision.RunningMode.VIDEO,   # los frames vienen en secuencia
        num_poses=1,                                # detectar una sola persona
        min_pose_detection_confidence=0.6,          # confianza para encontrarla
        min_pose_presence_confidence=0.6,           # confianza para creer que sigue ahí
        min_tracking_confidence=0.6,                # confianza para seguirla entre frames
        output_segmentation_masks=False,            # no hace falta recortar la silueta
    )
    return mp_vision.PoseLandmarker.create_from_options(opciones)   # armar el detector
```

`RunningMode.VIDEO` le avisa a MediaPipe que los frames son consecutivos, así usa
el anterior para seguir a la persona en vez de buscarla de cero cada vez.

---

## 5. Filtros

### FiltroUnEuro

```python
class FiltroUnEuro:
    def __init__(self, corte, beta, corte_derivada=1.0):
        self.corte = corte                   # cuánto suaviza en reposo
        self.beta = beta                     # cuánto se afloja al moverse
        self.corte_derivada = corte_derivada # suavizado de la velocidad
        self._x = None                       # último valor suavizado
        self._dx = 0.0                       # última velocidad estimada
        self._t = None                       # instante de la última llamada
```

El guion bajo adelante (`_x`) es una convención de Python: avisa que esa variable
es de uso interno y no se toca desde afuera.

```python
    @staticmethod
    def _alfa(corte, dt):
        tau = 1.0 / (2.0 * np.pi * corte)    # constante de tiempo del filtro
        return 1.0 / (1.0 + tau / dt)        # peso entre 0 y 1
```

Convierte una frecuencia de corte en un peso.

> Con `alfa = 0.1`, el valor nuevo pesa 10% y el viejo 90%: suaviza mucho. Con
> `alfa = 0.9` es al revés: casi no suaviza.

`@staticmethod` significa que la función no usa nada del objeto: es una cuenta
suelta que vive adentro de la clase por orden.

```python
    def __call__(self, x, t):
        x = np.asarray(x, dtype=float)       # aceptar listas o arrays indistintamente
        if self._x is None or t <= self._t:  # primera llamada, o tiempo que no avanzó
            self._x, self._t = x, t          # guardar y devolver sin filtrar
            return x
```

`__call__` hace que el objeto se pueda usar como si fuera una función:
`filtro(valor, tiempo)` en vez de `filtro.aplicar(valor, tiempo)`.

```python
        dt = t - self._t                     # segundos desde la llamada anterior
        alfa_d = self._alfa(self.corte_derivada, dt)
        self._dx = alfa_d * (x - self._x) / dt + (1 - alfa_d) * self._dx
```

`(x - self._x) / dt` es la velocidad: cuánto se movió dividido el tiempo que
tardó. Esa velocidad también se suaviza, para que no salte.

```python
        corte = self.corte + self.beta * float(np.linalg.norm(self._dx))
        alfa = self._alfa(corte, dt)         # peso según ese corte
        self._x = alfa * x + (1 - alfa) * self._x   # mezclar nuevo y viejo
        self._t = t                          # recordar el instante
        return self._x
```

Aquí reside la idea del filtro: **el corte depende de la velocidad**.

> Con el punto quieto la velocidad es ~0, el corte queda en 1.0 y `alfa` sale
> chico: suaviza fuerte. Con el punto a 0.8 m/s el corte sube a 9, `alfa` se
> acerca a 1 y el filtro casi no interviene, así que no mete retardo.

`np.linalg.norm` es el largo del vector: convierte una velocidad en 3D en un solo
número.

### Suavizador

```python
class Suavizador:
    def __init__(self, corte, beta):
        self._corte = corte                  # ajustes que heredan los filtros
        self._beta = beta
        self._filtros = {}                   # un filtro por cada punto

    def __call__(self, clave, valor, t):
        if clave not in self._filtros:       # ¿primera vez con este punto?
            self._filtros[clave] = FiltroUnEuro(self._corte, self._beta)   # crearlo
        return self._filtros[clave](valor, t)    # aplicarlo

    def reiniciar(self):
        self._filtros.clear()                # olvidar todo el historial
```

Cada punto necesita su propio filtro con su propia memoria: el del codo no puede
mezclarse con el del hombro. Esta clase los crea a medida que aparecen y los
guarda en un diccionario, para no declarar 33 filtros a mano.

---

## 6. Medición

### mejorar_contraste

```python
def mejorar_contraste(bgr, clahe):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)   # pasar a espacio LAB
    l, a, b = cv2.split(lab)                     # separar brillo (L) de color (a, b)
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)
```

La última línea hace tres cosas: aplica el realce solo al brillo, vuelve a unir
los tres canales y convierte de nuevo a BGR.

> LAB separa "qué tan claro es" de "de qué color es". Realzar solo `L` aclara las
> sombras sin volver la piel naranja ni la ropa violeta.

### calcular_angulo

```python
def calcular_angulo(a, b, c):
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))   # a arrays de numpy
    ba, bc = a - b, c - b                        # los dos vectores que salen de b

    norma = np.linalg.norm(ba) * np.linalg.norm(bc)   # producto de los dos largos
    if norma == 0:                               # dos puntos encimados: no hay ángulo
        return None

    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / norma, -1.0, 1.0))))
```

Calcula el ángulo que se forma **en `b`**, el punto del medio. Para el curl: `a`
es el hombro, `b` el codo y `c` la mano. Para la sentadilla: cadera, rodilla y
pie. La función no sabe ni le importa de qué articulación se trata.

La última línea, leída de adentro hacia afuera:

| Paso | Qué hace |
|------|----------|
| `np.dot(ba, bc)` | Producto punto de los dos vectores |
| `/ norma` | Lo convierte en el coseno del ángulo |
| `np.clip(..., -1, 1)` | Lo encierra en el rango válido del coseno |
| `np.arccos(...)` | Del coseno saca el ángulo, en radianes |
| `np.degrees(...)` | Radianes a grados |

**Por qué el `clip`.** El coseno siempre vale entre −1 y 1, pero los redondeos de
la computadora pueden dar 1.0000000002. `arccos` de ese número no existe y el
programa se caería. `clip` lo recorta a 1 y listo.

> Por ejemplo, `calcular_angulo([0, 0], [0, 1], [1, 1])` devuelve 90°.

### confianza y confianza_grupo

```python
def confianza(lm):
    valores = [
        v
        for v in (getattr(lm, "visibility", None), getattr(lm, "presence", None))
        if v is not None                     # descartar los que vengan vacíos
    ]
    return min(valores) if valores else 1.0  # el menor; si no hay ninguno, confiar
```

MediaPipe reporta dos números de confianza por punto, pero puede dejarlos en
`None`. En Python, comparar `None < 0.5` lanza un error y tira el programa, así
que hay que descartarlos antes.

`getattr(objeto, "campo", None)` pide un campo sin romperse si no existe.

```python
def confianza_grupo(landmarks, indices):
    return max(confianza(landmarks[i]) for i in indices)
```

La confianza de un grupo es la del **mejor** de sus landmarks: si al menos uno se
ve bien, el grupo sirve.

### punto_grupo

```python
def punto_grupo(mundo, landmarks, indices):
    puntos, pesos = [], []                   # coordenadas y confianzas
    for i in indices:                        # los landmarks del grupo
        c = confianza(landmarks[i])
        if c > 0.05:                         # ignorar los completamente perdidos
            puntos.append([mundo[i].x, mundo[i].y, mundo[i].z])
            pesos.append(c)

    if not puntos:                           # ninguno sirve
        return None
    return np.average(np.asarray(puntos), axis=0, weights=pesos)
```

Devuelve un punto 3D que representa toda la articulación. Con un grupo de un solo
landmark, devuelve ese landmark; con la muñeca o el tobillo, promedia.

`np.average` con `weights` hace un promedio ponderado: los que se ven mejor pesan
más.

> Con la muñeca en 0.16 y el meñique en 0.82, el resultado cae casi encima del
> meñique. Como los cuatro están sobre la misma línea del antebrazo, el ángulo
> casi no cambia.

### longitudes_plausibles

```python
def longitudes_plausibles(a, b, c, historial):
    primero = float(np.linalg.norm(np.asarray(a) - np.asarray(b)))   # a → b
    segundo = float(np.linalg.norm(np.asarray(b) - np.asarray(c)))   # b → c

    if primero <= 0 or segundo <= 0:         # puntos encimados: imposible
        return False, None
    if len(historial) < 10:                  # todavía no hay con qué comparar
        return True, (primero, segundo)

    referencia = np.median(np.asarray(historial), axis=0)   # largos típicos
    desvio = np.abs(np.array([primero, segundo]) - referencia) / referencia
    return bool(np.all(desvio <= TOLERANCIA_LONGITUD)), (primero, segundo)
```

Verifica que el punto del medio esté donde debería. Los dos segmentos son huesos:
su largo no cambia. Si el modelo se inventa la articulación, el número se
dispara.

Funciona igual para brazo/antebrazo que para muslo/pantorrilla, porque no sabe
qué está midiendo.

`np.median` toma el valor del medio, no el promedio, así que un frame malo no
contamina la referencia. `np.all` exige que **los dos** huesos estén dentro de la
tolerancia.

### elegir_lado

```python
def elegir_lado(landmarks, lado_actual, ejercicio):
    if LADO != "auto":                       # el usuario fijó un lado
        return LADO

    extremos = (ejercicio["puntos"][0], ejercicio["puntos"][2])   # los dos de afuera
    puntajes = {}
    for nombre, grupos in PUNTOS.items():    # "derecho" e "izquierdo"
        puntajes[nombre] = min(
            confianza_grupo(landmarks, grupos[p]) for p in extremos
        )
```

Le pone puntaje a cada lado: el peor de los dos puntos externos del ejercicio.
El vértice se excluye a propósito, porque su confianza es la menos fiable.

```python
    mejor = max(puntajes, key=puntajes.get)  # el lado con mejor puntaje
    if lado_actual is None or puntajes[lado_actual] < UMBRAL_VISIBILIDAD:
        if lado_actual is None or puntajes[mejor] > puntajes[lado_actual] + 0.25:
            return mejor                     # recién ahí se cambia
    return lado_actual                       # en cualquier otro caso, no tocar
```

Las dos condiciones anidadas hacen que la decisión sea **pegajosa**: mientras el
lado actual siga por encima del umbral no se cambia, y para cambiar el otro tiene
que superarlo por 0.25. Sin esto, la elección salta de un lado a otro y rompe el
conteo a mitad de una repetición.

`max(puntajes, key=puntajes.get)` devuelve la **clave** con el valor más alto, o
sea `"derecho"` o `"izquierdo"`.

---

## 7. Máquina de repeticiones

```python
class MaquinaRepeticiones:
    def __init__(self, ejercicio):
        self.ejercicio = ejercicio           # config del ejercicio activo
        self.contador = 0                    # repeticiones acumuladas
        self.estado = None                   # "up", "down" o None al arrancar
        self._historial = deque(maxlen=VENTANA_CALIBRACION)   # últimos 300 ángulos
        self._ultima = 0.0                   # instante de la última repetición
```

La máquina recibe el ejercicio completo, así saca de ahí sus umbrales y su
amplitud mínima. Al cambiar de ejercicio se crea una máquina nueva.

```python
    @property
    def recorrido(self):
        if len(self._historial) < 30:        # menos de 1 segundo de datos
            return None

        muestras = np.asarray(self._historial)
        bajo, alto = np.percentile(muestras, (5, 95))   # casi el mínimo y casi el máximo
        recorrido = alto - bajo              # cuánto se mueve en realidad
```

`@property` permite escribir `maquina.recorrido` en vez de `maquina.recorrido()`:
se usa como si fuera un dato, aunque por dentro calcule.

> **Percentil 5 y 95.** Al ordenar 100 mediciones de menor a mayor, corresponden
> a la que ocupa la posición 5 y a la que ocupa la 95. Los extremos crudos
> recogen el ruido; los percentiles lo descartan.

```python
        if recorrido < self.ejercicio["amplitud_min"]:   # movimiento muy chico
            return None
        if np.median(np.abs(np.diff(muestras))) > RUIDO_MAXIMO * recorrido:
            return None                      # la señal no es suave: es temblor

        return float(bajo), float(alto)
```

La amplitud mínima sale del ejercicio, no de una constante global: la elevación
lateral recorre mucho menos que un curl y necesita un valor más bajo.

`np.diff` da la diferencia entre valores consecutivos, y la mediana de esos
saltos mide qué tan brusca es la señal.

> Un curl real cambia unos 2° por frame y recorre 88°: suave. Puro ruido cambia
> 19° por frame y "recorre" 66°: brusco. El recorrido se parece; la suavidad los
> separa.

```python
    @property
    def umbrales(self):
        if not CALIBRACION_AUTOMATICA:       # modo manual: los del ejercicio
            return self.ejercicio["flexionado"], self.ejercicio["extendido"]

        recorrido = self.recorrido
        if recorrido is None:                # todavía no se sabe el recorrido
            return None

        bajo, alto = recorrido
        margen = MARGEN_UMBRAL * (alto - bajo)   # 15% del recorrido
        return bajo + margen, alto - margen      # umbrales metidos hacia adentro
```

> Con un recorrido de 82° a 165°, el margen es `0.15 × 83 = 12.5`. Los umbrales
> quedan en 94.5° y 152.5°: hay que completar el 85% del movimiento.

Devolver `None` es importante: equivale a declarar que el recorrido todavía no
se conoce y que, por lo tanto, no corresponde contar. No existen umbrales de
respaldo, porque un par de ángulos fijos o queda fuera del alcance del
movimiento —y entonces no cuenta nunca— o resulta tan amplio que el ruido lo
cruza por sí solo.

```python
    def actualizar(self, angulo, ahora):
        self._historial.append(angulo)       # guardar para la calibración

        umbrales = self.umbrales
        if umbrales is None:                 # sin calibrar: solo acumular
            return

        flexionado, extendido = umbrales
        nuevo = self.estado                  # por defecto, no cambiar
        if angulo < flexionado:
            nuevo = "up"                     # articulación doblada
        elif angulo > extendido:
            nuevo = "down"                   # articulación estirada
```

Entre los dos umbrales el estado no cambia. Esa zona muerta es la **histéresis**,
lo mismo que hace un termostato que prende a 19° y apaga a 21°: sin ella, el
ruido alrededor de un único umbral dispararía varios conteos seguidos.

```python
        contar_en = self.ejercicio["contar_en"]
        objetivo = ("down", "up") if contar_en == "up" else ("up", "down")
        if (self.estado, nuevo) == objetivo and ahora - self._ultima > DURACION_MIN_REP:
            self.contador += 1
            self._ultima = ahora

        self.estado = nuevo                  # el nuevo pasa a ser el actual
```

La clase no imprime nada: avisar por consola es tarea de la interfaz, no de la
lógica. Esa separación es también la que permite probarla sin ensuciar la salida
de los tests.

Aquí reside lo que permite que un mismo motor sirva para los cuatro ejercicios. Se
compara **la transición** `(anterior, nuevo)`, y `contar_en` decide cuál cuenta:

- En el curl y la sentadilla, la repetición termina al doblar → `("down", "up")`.
- En el press y la elevación, termina al estirar → `("up", "down")`.

En los dos casos hay que pasar por el otro extremo antes de poder contar de
nuevo.

```python
    def reiniciar(self):
        self.contador = 0
        self.estado = None
        self._historial.clear()              # la calibración vuelve a empezar
```

---

## 8. Dibujo en pantalla

### dibujar_esqueleto

```python
def dibujar_esqueleto(image, puntos_px, visibles, destacados=()):
    for inicio, fin in POSE_CONNECTIONS:
        if visibles[inicio] and visibles[fin]:    # solo si ambos extremos sirven
            cv2.line(image, puntos_px[inicio], puntos_px[fin], (245, 117, 66), 2)

    for i, punto in enumerate(puntos_px):
        if i in destacados:                       # los tres que se están midiendo
            cv2.circle(image, punto, 9, (0, 255, 0) if visibles[i] else (0, 0, 255), -1)
            cv2.circle(image, punto, 11, (255, 255, 255), 2)   # aro blanco alrededor
        elif visibles[i]:
            cv2.circle(image, punto, 4, (245, 66, 230), -1)    # el resto, chiquito
```

**Los colores van en BGR, no RGB.** Es una particularidad histórica de OpenCV:
`(0, 255, 0)` es verde y `(0, 0, 255)` es rojo, al revés de lo habitual.

El `-1` como grosor significa "relleno". `enumerate` recorre la lista dando el
índice y el valor a la vez.

### texto_legible

```python
def texto_legible(image, texto, origen, escala=0.6, color=(255, 255, 255), grosor=2):
    x, y = origen
    for dx, dy in CONTORNO:                  # ocho copias corridas
        cv2.putText(
            image,
            texto,
            (x + dx, y + dy),                # posición corrida
            FUENTE,
            escala,
            (0, 0, 0),                       # todas en negro
            grosor,
            cv2.LINE_AA,                     # bordes suavizados
        )
    cv2.putText(image, texto, origen, FUENTE, escala, color, grosor, cv2.LINE_AA)
```

Dibuja el texto ocho veces en negro, corrido un par de píxeles en cada dirección,
y una novena vez encima en color. Eso arma un contorno que lo hace legible sobre
cualquier fondo.

**Lo importante es que las nueve pasadas usan el mismo `grosor`.** En OpenCV el
ancho de las letras depende del grosor del trazo, así que dibujar el contorno más
grueso que el relleno desfasa las dos versiones y el texto se ve doble.

### dibujar_panel

```python
def dibujar_panel(image, contador, estado, aviso, ejercicio):
    cv2.rectangle(image, (0, 0), (250, 90), (245, 117, 16), -1)   # fondo naranja
    cv2.putText(image, "REPETICIONES", (10, 20), FUENTE, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        image, str(contador), (10, 70), FUENTE, 1.5, (255, 255, 255), 2, cv2.LINE_AA
    )
    cv2.putText(image, "ESTADO", (120, 20), FUENTE, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        image, estado or "-", (120, 70), FUENTE, 1, (255, 255, 255), 2, cv2.LINE_AA
    )

    texto_legible(image, ejercicio["nombre"], (10, 118), 0.6)     # ejercicio activo
    texto_legible(image, "ponete " + ejercicio["vista"], (10, 142), 0.5, (120, 220, 255))
    texto_legible(image, "e = cambiar ejercicio", (10, 166), 0.45, (200, 200, 200), 1)

    if aviso:                                # solo cuando hay algo que decir
        texto_legible(image, aviso, (10, 196), 0.6, (80, 80, 255))
```

`estado or "-"` es un atajo de Python: si `estado` es `None`, usa `"-"`.

Las coordenadas son `(x, y)` desde la **esquina superior izquierda**, con `y`
creciendo hacia abajo. Por eso los textos van bajando: 118, 142, 166, 196.

### dibujar_menu

```python
def dibujar_menu(image, clave_actual):
    alto, ancho = image.shape[:2]
    cv2.addWeighted(np.zeros_like(image), 0.65, image, 0.35, 0, image)
```

`addWeighted` mezcla dos imágenes. Al mezclar con una imagen toda negra al 65%,
se atenúa el frame entero para que el menú resalte. El último argumento hace que
el resultado se escriba sobre `image` misma.

```python
    ancho_caja = 460
    alto_caja = 120 + 50 * len(EJERCICIOS)   # crece con la cantidad de ejercicios
    x0 = (ancho - ancho_caja) // 2           # centrar horizontalmente
    y0 = (alto - alto_caja) // 2             # y verticalmente
```

La caja se dimensiona sola: al incorporar un quinto ejercicio, aumenta su altura.

```python
    caja = image[y0 : y0 + alto_caja, x0 : x0 + ancho_caja]     # recorte de la zona
    cv2.addWeighted(np.zeros_like(caja), 0.75, caja, 0.25, 0, caja)   # oscurecerla más
    cv2.rectangle(
        image, (x0, y0), (x0 + ancho_caja, y0 + alto_caja), (245, 117, 16), 2
    )                                        # borde naranja
```

`image[y0:y0+alto, x0:x0+ancho]` no copia: es una **vista** del mismo array, así
que escribir en `caja` modifica `image`.

```python
    texto_legible(image, "ELEGIR EJERCICIO", (x0 + 30, y0 + 45), 0.75)
    for i, (clave, ejercicio) in enumerate(EJERCICIOS.items(), start=1):
        actual = clave == clave_actual       # ¿es el que está activo?
        color = (0, 255, 0) if actual else (245, 245, 245)   # verde o blanco
        marca = ">" if actual else " "
        texto_legible(
            image,
            f"{marca} {i}   {ejercicio['nombre']}",
            (x0 + 30, y0 + 45 + i * 50),     # cada opción 50 px más abajo
            0.7,
            color,
        )
        texto_legible(
            image,
            ejercicio["vista"],              # la orientación, en chiquito
            (x0 + 75, y0 + 66 + i * 50),
            0.4,
            (150, 200, 230),
            1,
        )
```

`enumerate(..., start=1)` numera desde 1, que es la tecla que hay que apretar.

```python
    texto_legible(
        image,
        "numero = elegir     e = cerrar",
        (x0 + 30, y0 + alto_caja - 25),      # pegado al borde de abajo
        0.5,
        (200, 200, 200),
        1,
    )
```

### redactar_aviso

```python
def redactar_aviso(vis, ejercicio, angulo, calibrada):
    if not vis:                              # el diccionario está vacío
        return "No detecto a nadie en la imagen"

    extremos = (ejercicio["puntos"][0], ejercicio["puntos"][2])
    flojos = [NOMBRES[p] for p in extremos if vis[p] < UMBRAL_VISIBILIDAD]
    if flojos:
        return "No veo bien " + " ni ".join(flojos)
    if angulo is None:                       # el vértice no pasó la validación
        return "No puedo ubicar " + NOMBRES[ejercicio["puntos"][1]] + " con seguridad"
    if not calibrada:                        # mide bien, pero falta el recorrido
        return "Calibrando: hace una repeticion completa y lenta"
    return None                              # todo en orden: sin aviso
```

El mensaje se arma con los nombres del ejercicio activo, así que en la sentadilla
dice "No veo bien el pie" y en el curl "No veo bien la mano".

El cuarto caso es el que evita que el programa falle en silencio: si mide bien
pero todavía no conoce el recorrido, lo informa en lugar de limitarse a no contar.

`" ni ".join(["el hombro", "la mano"])` arma `"el hombro ni la mano"`.

Si los dos extremos se ven bien pero igual no hubo medición, el que falló fue el
vértice en la validación geométrica: se deduce por descarte.

---

## 9. El bucle principal

### Preparación

```python
def main():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)      # abrir la webcam por defecto
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUCION[0])    # pedir 1280 de ancho
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUCION[1])   # y 720 de alto

    if not cap.isOpened():                        # la cámara no respondió
        print("No se pudo abrir la camara.")
        return
```

El `0` es la primera cámara del sistema. `CAP_DSHOW` es el backend de Windows,
que la abre bastante más rápido que el predeterminado.

Los `set` son **pedidos**, no órdenes: si la cámara no soporta esa resolución,
entrega la más parecida.

```python
    try:
        landmarker = cargar_landmarker()          # el detector de pose
    except RuntimeError as error:                 # sin internet la primera vez
        print(error)
        cap.release()                             # soltar la cámara ya abierta
        return

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))   # el realce
    suave = Suavizador(FILTRO_CORTE, FILTRO_BETA) # los filtros

    clave = EJERCICIO                             # ejercicio activo
    ejercicio = EJERCICIOS[clave]                 # su configuración
    maquina = MaquinaRepeticiones(ejercicio)      # el contador
```

El objeto CLAHE se crea **una sola vez**: rearmarlo en cada frame sería caro.
`tileGridSize=(8, 8)` divide la imagen en 64 zonas y realza cada una por
separado; por eso funciona con una parte quemada y otra oscura.

```python
    menu = False                                  # el menú arranca cerrado
    lado = None                                   # lado activo, todavía sin elegir
    rango = [None, None]                          # mínimo y máximo vistos
    longitudes = deque(maxlen=60)                 # largos aceptados
    fallos = 0                                    # lecturas fallidas seguidas
    ultimo_ms = -1                                # último timestamp enviado
    t0 = time.perf_counter()                      # instante de arranque
```

### Leer el frame

```python
    while True:
        ret, frame = cap.read()                   # ret = si salió bien
        if not ret:
            fallos += 1
            if fallos > 30:                       # 30 fallos seguidos: rendirse
                print("Se perdio la conexion con la camara.")
                break
            continue                              # saltear este frame y seguir
        fallos = 0                                # salió bien: reiniciar la cuenta
```

Una webcam USB puede fallar una lectura sin estar desconectada, así que un solo
fallo no termina el programa.

`continue` salta al principio del `while`; `break` sale del bucle.

```python
        if ESPEJO:
            frame = cv2.flip(frame, 1)            # 1 = invertir horizontalmente
        if MEJORAR_CONTRASTE:
            frame = mejorar_contraste(frame, clahe)
```

### Detectar

```python
        ahora = time.perf_counter() - t0          # segundos desde el arranque
        ultimo_ms = max(int(ahora * 1000), ultimo_ms + 1)   # forzar que siempre crezca

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),   # OpenCV da BGR, MediaPipe pide RGB
        )
        resultados = landmarker.detect_for_video(mp_image, ultimo_ms)
```

El timestamp tiene que ser el tiempo **real**, porque MediaPipe lo usa para su
seguimiento interno. El `max(..., ultimo_ms + 1)` garantiza que siempre crezca:
si dos frames caen en el mismo milisegundo, `detect_for_video` da error.

### Medir el ángulo

```python
        alto, ancho = frame.shape[:2]             # dimensiones de la imagen
        angulo = None                             # sin medición todavía
        vis = {}                                  # confianzas de este frame
        vertice_px = None                         # dónde escribir el ángulo

        if resultados.pose_landmarks and resultados.pose_world_landmarks:
            landmarks = resultados.pose_landmarks[0]        # coordenadas de imagen
            mundo = resultados.pose_world_landmarks[0]      # coordenadas en metros
```

Se comprueban **las dos** listas. MediaPipe puede devolver los puntos de imagen
sin los del mundo, y pedir el `[0]` de una lista vacía tira el programa.

`shape` de una imagen da `(alto, ancho, canales)`; el `[:2]` toma los dos
primeros.

```python
            anterior, lado = lado, elegir_lado(landmarks, lado, ejercicio)
            if lado != anterior and anterior is not None:
                longitudes.clear()                # el historial era del otro lado
            grupos = PUNTOS[lado]                 # los landmarks de ese lado
```

```python
            nombres = ejercicio["puntos"]         # las tres articulaciones
            vis = {p: confianza_grupo(landmarks, grupos[p]) for p in nombres}
            extremos_ok = all(
                vis[p] >= UMBRAL_VISIBILIDAD for p in (nombres[0], nombres[2])
            )
```

Solo se les exige confianza a los dos puntos **externos**. La del vértice se
guarda para el diagnóstico, pero no se usa como filtro, porque MediaPipe la
reporta mal.

```python
            if extremos_ok:
                medidos = [
                    punto_grupo(mundo, landmarks, grupos[p]) for p in nombres
                ]
                if all(p is not None for p in medidos):    # los tres se pudieron armar
                    a, b, c = (
                        suave(p, v, ahora) for p, v in zip(nombres, medidos)
                    )
                    valido, medidas = longitudes_plausibles(a, b, c, longitudes)
                    if valido:
                        longitudes.append(medidas)         # sumar a la referencia
                        angulo = calcular_angulo(a, b, c)
```

`zip(nombres, medidos)` empareja cada nombre con su punto, así el suavizador usa
el nombre como clave de su filtro.

El orden importa: primero suavizar, después validar, y recién ahí calcular. Si la
validación falla, `angulo` queda en `None` y el conteo se pausa.

### Dibujar

```python
            puntos_px = []
            for i, lm in enumerate(landmarks):
                x, y = suave(i, [lm.x, lm.y], ahora) * [ancho, alto]   # de 0-1 a píxeles
                puntos_px.append((int(x), int(y)))     # OpenCV quiere enteros
            visibles = [confianza(lm) >= UMBRAL_VISIBILIDAD for lm in landmarks]
```

Las coordenadas de imagen van de 0 a 1, así que multiplicarlas por el ancho y el
alto da píxeles. También se suavizan, para que los marcadores no bailen.

```python
            destacados = set()
            for orden, p in enumerate(nombres):
                principal = grupos[p][0]          # el primer landmark del grupo
                destacados.add(principal)
                if orden == 1:                    # el del medio es el vértice
                    visibles[principal] = angulo is not None
                else:
                    visibles[principal] = vis[p] >= UMBRAL_VISIBILIDAD
```

Los tres marcadores se pintan según el criterio real con el que fueron aceptados,
no según su confianza cruda. El vértice se pinta verde solo si el ángulo se pudo
calcular, o sea si pasó la validación geométrica.

```python
            vertice_px = puntos_px[grupos[nombres[1]][0]]   # dónde va el número
            dibujar_esqueleto(
                image=frame,
                puntos_px=puntos_px,
                visibles=visibles,
                destacados=destacados,
            )
```

### Contar

```python
        if angulo is not None and not menu:
            rango[0] = angulo if rango[0] is None else min(rango[0], angulo)
            rango[1] = angulo if rango[1] is None else max(rango[1], angulo)
            antes = maquina.contador
            maquina.actualizar(angulo, ahora)      # acá se cuenta
            if maquina.contador != antes:          # hubo repeticion nueva
                print(f"{ejercicio['nombre']}: {maquina.contador}")
```

El `and not menu` es lo que **pausa el conteo mientras el menú está abierto**. La
detección continúa en ejecución, pero no se suman repeticiones durante la selección.

```python
        if angulo is not None and vertice_px is not None:
            x, y = vertice_px
            texto_legible(frame, f"{int(angulo)}", (x + 18, y - 14))   # corrido del marcador
```

El `+18, -14` corre el número para que no tape el círculo verde.

```python
        if menu:
            dibujar_menu(frame, clave)             # el menú reemplaza al panel
        else:
            dibujar_panel(
                frame,
                maquina.contador,
                maquina.estado,
                redactar_aviso(vis, ejercicio, angulo, maquina.umbrales is not None),
                ejercicio,
            )
        cv2.imshow(VENTANA, frame)                 # mostrar el frame terminado
```

Se dibuja uno **o** el otro: si se dibujaran los dos, el menú taparía a medias el
panel y quedaría ilegible.

### Teclado y salida

```python
        tecla = cv2.waitKey(1) & 0xFF             # esperar 1 ms por una tecla
        if tecla == ord("q"):
            break
        if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
            break                                 # cerraron la ventana con la ✕
```

**`waitKey` no se puede sacar**, aunque no uses el teclado: es lo que le da tiempo
a OpenCV para refrescar la ventana. Sin esa llamada, la imagen no se actualiza.

`& 0xFF` se queda con los últimos 8 bits, porque algunos sistemas devuelven
basura en los bits altos. `ord("q")` da el número que representa a esa letra.

```python
        if tecla == ord("e"):
            menu = not menu                       # abrir o cerrar
        if menu and ord("1") <= tecla <= ord("9"):
            claves = list(EJERCICIOS)             # las claves en orden
            elegida = tecla - ord("1")            # "1" → 0, "2" → 1, etc.
            if elegida < len(claves):             # ignorar números de más
                clave = claves[elegida]
                ejercicio = EJERCICIOS[clave]
                maquina = MaquinaRepeticiones(ejercicio)   # contador nuevo
                suave.reiniciar()                 # los filtros eran de otro punto
                longitudes.clear()                # los largos eran de otro miembro
                rango = [None, None]
                lado = None                       # volver a elegir el lado
                menu = False                      # cerrar el menú
```

Al cambiar de ejercicio hay que tirar **todo** el estado acumulado: pertenecía a
otras articulaciones y contaminaría las mediciones nuevas.

`if elegida < len(claves)` evita que apretar 7 con cuatro ejercicios rompa el
programa.

```python
        if tecla == ord("r"):
            maquina.reiniciar()                   # contador y calibración
            suave.reiniciar()                     # memoria de los filtros
            longitudes.clear()                    # referencia de largos
            rango = [None, None]
        if tecla == ord("d"):
            umbrales = maquina.umbrales
            detalle = (
                f"{umbrales[0]:.0f}/{umbrales[1]:.0f}"
                if umbrales
                else f"sin calibrar (hace falta un recorrido de {ejercicio['amplitud_min']} grados)"
            )
            print(
                f"ejercicio={clave} lado={lado} angulo={angulo} rango={rango} "
                f"umbrales={detalle} "
                f"vis={ {k: round(v, 2) for k, v in vis.items()} }"
            )
```

`d` imprime el diagnóstico por consola, para no ensuciar la imagen.
`{flexionado:.0f}` formatea el número sin decimales.

```python
    cap.release()                                 # soltar la cámara
    cv2.destroyAllWindows()                       # cerrar las ventanas
    landmarker.close()                            # liberar el modelo


if __name__ == "__main__":
    main()
```

Liberar la cámara es importante: si no, queda tomada y otro programa no puede
usarla.

La última línea significa "si este archivo se ejecuta directamente, arrancá". Si
en cambio alguien lo importa desde otro archivo, no arranca solo.

---

## Cómo entender un código

Técnicas aplicables a cualquier código, no solo a este.

### 1. Comenzar por el final, no por el principio

Conviene localizar `main()` o el punto de entrada y leerlo en primer lugar,
porque ofrece el mapa general: qué ocurre y en qué orden. Recién después tiene
sentido descender a las funciones concretas.

La lectura de arriba hacia abajo resulta la menos eficaz: obliga a empezar por
cuarenta constantes sueltas sin conocer su finalidad.

### 2. Leer los nombres antes que el contenido

```bash
grep -n "^def \|^class " contador_repeticiones.py
```

El resultado condensa el índice del archivo en una sola pantalla. Si los nombres
están bien elegidos, permite comprender buena parte del programa sin leer una
línea de lógica.

### 3. Ejecutar fragmentos aislados

No es necesario ejecutar el programa completo para entender una función:

```python
import contador_repeticiones as m
print(m.calcular_angulo([0, 0], [0, 1], [1, 1]))   # 90.0
```

Conviene probar con valores cuyo resultado se conozca de antemano y comprobar
que coincida con lo esperado. Este método aporta más que la lectura prolongada.

### 4. Insertar `print` en puntos intermedios

Es la forma más simple y efectiva de observar el comportamiento real: imprimir
una variable inmediatamente antes de la línea que no se comprende. Si el valor
que aparece difiere del esperado, ahí se localiza el malentendido.

### 5. Preguntarse qué ocurre al eliminar una línea

Comentar una línea y ejecutar de nuevo. Si nada cambia, esa línea no cumplía la
función que se le atribuía. Si el programa falla, queda en evidencia su
propósito.

> Un ejemplo: eliminar el `np.clip` de `calcular_angulo` y pasarle tres puntos
> alineados.

### 6. Distinguir el "qué" del "por qué"

El código expresa **qué** hace; rara vez explica **por qué**. Cuando una
solución parece innecesariamente compleja, suele responder a una razón que no
resulta visible: un error detectado en su momento, o una limitación de la
librería.

Ese es el motivo por el que este proyecto separa los documentos: el `.py`
contiene el qué, y [DISENO.md](DISENO.md) el por qué.

### 7. Seguir un dato de extremo a extremo

Resulta útil rastrear un único dato: dónde se origina, qué lo modifica y dónde
termina.

> En este caso: un punto proviene de MediaPipe → pasa por el suavizador → entra
> en el cálculo del ángulo → alimenta la máquina de estados → incrementa el
> contador.

Cinco pasos. Todo lo demás son detalles que dependen de esa secuencia.

### 8. No intentar comprender todo de una vez

Es válido tratar una función como una caja negra cuando su nombre resulta
suficiente. No hace falta conocer el funcionamiento interno de CLAHE para
entender que mejora el contraste. El detalle puede abordarse más adelante, si
llega a ser necesario.
