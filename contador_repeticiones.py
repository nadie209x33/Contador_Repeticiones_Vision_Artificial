import os
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

EJERCICIO = "curl"
LADO = "auto"
MODELO = "full"
ESPEJO = True
MEJORAR_CONTRASTE = True

DURACION_MIN_REP = 0.5
MARGEN_UMBRAL = 0.15
RUIDO_MAXIMO = 0.15
VENTANA_CALIBRACION = 300
CALIBRACION_AUTOMATICA = True

UMBRAL_VISIBILIDAD = 0.5
TOLERANCIA_LONGITUD = 0.4
FILTRO_CORTE = 1.0
FILTRO_BETA = 10.0

TAMANO_MINIMO_MODELO = 1_000_000
RESOLUCION = (1280, 720)
VENTANA = "Contador de repeticiones"

PUNTOS = {
    "derecho": {
        "hombro": (12,),
        "codo": (14,),
        "muneca": (16, 18, 20, 22),
        "cadera": (24,),
        "rodilla": (26,),
        "tobillo": (28, 30, 32),
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

EJERCICIOS = {
    "curl": {
        "nombre": "Curl de biceps",
        "vista": "de perfil",
        "puntos": ("hombro", "codo", "muneca"),
        "contar_en": "up",
        "amplitud_min": 50,
        "flexionado": 55,
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
        "contar_en": "ciclo",
        "amplitud_min": 45,
        "flexionado": 80,
        "extendido": 160,
    },
    "elevacion": {
        "nombre": "Elevacion lateral",
        "vista": "de frente",
        "puntos": ("cadera", "hombro", "codo"),
        "contar_en": "ciclo",
        "amplitud_min": 35,
        "flexionado": 25,
        "extendido": 80,
    },
}

NOMBRES = {
    "hombro": "el hombro",
    "codo": "el codo",
    "muneca": "la mano",
    "cadera": "la cadera",
    "rodilla": "la rodilla",
    "tobillo": "el pie",
}

POSE_CONNECTIONS = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (27, 29),
    (27, 31),
    (24, 26),
    (26, 28),
    (28, 30),
    (28, 32),
    (15, 17),
    (15, 19),
    (15, 21),
    (16, 18),
    (16, 20),
    (16, 22),
]

FUENTE = cv2.FONT_HERSHEY_SIMPLEX
CONTORNO = ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, -2), (0, 2), (-2, 0), (2, 0))

MODEL_PATH = f"pose_landmarker_{MODELO}.task"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    f"pose_landmarker_{MODELO}/float16/latest/pose_landmarker_{MODELO}.task"
)


def descargar_modelo(destino=MODEL_PATH, url=MODEL_URL):
    parcial = destino + ".parcial"
    print("Descargando modelo de pose (solo la primera vez)...")
    try:
        urllib.request.urlretrieve(url, parcial)
        if os.path.getsize(parcial) < TAMANO_MINIMO_MODELO:
            raise OSError("el archivo descargado es demasiado chico")
        os.replace(parcial, destino)
    except Exception as error:
        if os.path.exists(parcial):
            os.remove(parcial)
        raise RuntimeError(
            f"No se pudo descargar el modelo desde {url}\n  {error}\n"
            "Revisar la conexion a internet y volver a ejecutar."
        ) from error


def cargar_landmarker():
    if not os.path.exists(MODEL_PATH):
        descargar_modelo()

    opciones = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
        output_segmentation_masks=False,
    )
    return mp_vision.PoseLandmarker.create_from_options(opciones)


class FiltroUnEuro:
    def __init__(self, corte, beta, corte_derivada=1.0):
        self.corte = corte
        self.beta = beta
        self.corte_derivada = corte_derivada
        self._x = None
        self._dx = 0.0
        self._t = None

    @staticmethod
    def _alfa(corte, dt):
        tau = 1.0 / (2.0 * np.pi * corte)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=float)
        if self._x is None or t <= self._t:
            self._x, self._t = x, t
            return x

        dt = t - self._t
        alfa_d = self._alfa(self.corte_derivada, dt)
        self._dx = alfa_d * (x - self._x) / dt + (1 - alfa_d) * self._dx

        corte = self.corte + self.beta * float(np.linalg.norm(self._dx))
        alfa = self._alfa(corte, dt)
        self._x = alfa * x + (1 - alfa) * self._x
        self._t = t
        return self._x


class Suavizador:
    def __init__(self, corte, beta):
        self._corte = corte
        self._beta = beta
        self._filtros = {}

    def __call__(self, clave, valor, t):
        if clave not in self._filtros:
            self._filtros[clave] = FiltroUnEuro(self._corte, self._beta)
        return self._filtros[clave](valor, t)

    def reiniciar(self):
        self._filtros.clear()


def mejorar_contraste(bgr, clahe):
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    return cv2.cvtColor(cv2.merge((clahe.apply(l), a, b)), cv2.COLOR_LAB2BGR)


def calcular_angulo(a, b, c):
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
    ba, bc = a - b, c - b

    norma = np.linalg.norm(ba) * np.linalg.norm(bc)
    if norma == 0:
        return None

    return float(np.degrees(np.arccos(np.clip(np.dot(ba, bc) / norma, -1.0, 1.0))))


def confianza(lm):
    valores = [
        v
        for v in (getattr(lm, "visibility", None), getattr(lm, "presence", None))
        if v is not None
    ]
    return min(valores) if valores else 1.0


def confianza_grupo(landmarks, indices):
    return max(confianza(landmarks[i]) for i in indices)


def punto_grupo(mundo, landmarks, indices):
    puntos, pesos = [], []
    for i in indices:
        c = confianza(landmarks[i])
        if c > 0.05:
            puntos.append([mundo[i].x, mundo[i].y, mundo[i].z])
            pesos.append(c)

    if not puntos:
        return None
    return np.average(np.asarray(puntos), axis=0, weights=pesos)


def longitudes_plausibles(a, b, c, historial):
    primero = float(np.linalg.norm(np.asarray(a) - np.asarray(b)))
    segundo = float(np.linalg.norm(np.asarray(b) - np.asarray(c)))

    if primero <= 0 or segundo <= 0:
        return False, None
    if len(historial) < 10:
        return True, (primero, segundo)

    referencia = np.median(np.asarray(historial), axis=0)
    desvio = np.abs(np.array([primero, segundo]) - referencia) / referencia
    return bool(np.all(desvio <= TOLERANCIA_LONGITUD)), (primero, segundo)


def elegir_lado(landmarks, lado_actual, ejercicio):
    if LADO != "auto":
        return LADO

    extremos = (ejercicio["puntos"][0], ejercicio["puntos"][2])
    puntajes = {}
    for nombre, grupos in PUNTOS.items():
        puntajes[nombre] = min(
            confianza_grupo(landmarks, grupos[p]) for p in extremos
        )

    mejor = max(puntajes, key=puntajes.get)
    if lado_actual is None or puntajes[lado_actual] < UMBRAL_VISIBILIDAD:
        if lado_actual is None or puntajes[mejor] > puntajes[lado_actual] + 0.25:
            return mejor
    return lado_actual


class MaquinaRepeticiones:
    def __init__(self, ejercicio):
        self.ejercicio = ejercicio
        self.contador = 0
        self.estado = None
        self._historial = deque(maxlen=VENTANA_CALIBRACION)
        self._ultima = 0.0

    @property
    def recorrido(self):
        if len(self._historial) < 30:
            return None

        muestras = np.asarray(self._historial)
        bajo, alto = np.percentile(muestras, (5, 95))
        recorrido = alto - bajo

        if recorrido < self.ejercicio["amplitud_min"]:
            return None
        if np.median(np.abs(np.diff(muestras))) > RUIDO_MAXIMO * recorrido:
            return None

        return float(bajo), float(alto)

    @property
    def umbrales(self):
        if not CALIBRACION_AUTOMATICA:
            return self.ejercicio["flexionado"], self.ejercicio["extendido"]

        recorrido = self.recorrido
        if recorrido is None:
            return None

        bajo, alto = recorrido
        margen = MARGEN_UMBRAL * (alto - bajo)
        return bajo + margen, alto - margen

    def actualizar(self, angulo, ahora):
        self._historial.append(angulo)

        umbrales = self.umbrales
        if umbrales is None:
            return

        flexionado, extendido = umbrales
        nuevo = self.estado
        if angulo < flexionado:
            nuevo = "up"
        elif angulo > extendido:
            nuevo = "down"

        contar_en = self.ejercicio["contar_en"]
        objetivo = ("down", "up") if contar_en == "up" else ("up", "down")
        if (self.estado, nuevo) == objetivo and ahora - self._ultima > DURACION_MIN_REP:
            self.contador += 1
            self._ultima = ahora

        self.estado = nuevo

    def reiniciar(self):
        self.contador = 0
        self.estado = None
        self._historial.clear()


def dibujar_esqueleto(image, puntos_px, visibles, destacados=()):
    for inicio, fin in POSE_CONNECTIONS:
        if visibles[inicio] and visibles[fin]:
            cv2.line(image, puntos_px[inicio], puntos_px[fin], (245, 117, 66), 2)

    for i, punto in enumerate(puntos_px):
        if i in destacados:
            cv2.circle(image, punto, 9, (0, 255, 0) if visibles[i] else (0, 0, 255), -1)
            cv2.circle(image, punto, 11, (255, 255, 255), 2)
        elif visibles[i]:
            cv2.circle(image, punto, 4, (245, 66, 230), -1)


def texto_legible(image, texto, origen, escala=0.6, color=(255, 255, 255), grosor=2):
    x, y = origen
    for dx, dy in CONTORNO:
        cv2.putText(
            image,
            texto,
            (x + dx, y + dy),
            FUENTE,
            escala,
            (0, 0, 0),
            grosor,
            cv2.LINE_AA,
        )
    cv2.putText(image, texto, origen, FUENTE, escala, color, grosor, cv2.LINE_AA)


def dibujar_panel(image, contador, estado, aviso, ejercicio):
    cv2.rectangle(image, (0, 0), (250, 90), (245, 117, 16), -1)
    cv2.putText(image, "REPETICIONES", (10, 20), FUENTE, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        image, str(contador), (10, 70), FUENTE, 1.5, (255, 255, 255), 2, cv2.LINE_AA
    )
    cv2.putText(image, "ESTADO", (120, 20), FUENTE, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(
        image, estado or "-", (120, 70), FUENTE, 1, (255, 255, 255), 2, cv2.LINE_AA
    )

    texto_legible(image, ejercicio["nombre"], (10, 118), 0.6)
    texto_legible(image, "ponete " + ejercicio["vista"], (10, 142), 0.5, (120, 220, 255))
    texto_legible(image, "e = cambiar ejercicio", (10, 166), 0.45, (200, 200, 200), 1)

    if aviso:
        texto_legible(image, aviso, (10, 196), 0.6, (80, 80, 255))


def dibujar_menu(image, clave_actual):
    alto, ancho = image.shape[:2]
    cv2.addWeighted(np.zeros_like(image), 0.65, image, 0.35, 0, image)

    ancho_caja = 460
    alto_caja = 120 + 50 * len(EJERCICIOS)
    x0 = (ancho - ancho_caja) // 2
    y0 = (alto - alto_caja) // 2

    caja = image[y0 : y0 + alto_caja, x0 : x0 + ancho_caja]
    cv2.addWeighted(np.zeros_like(caja), 0.75, caja, 0.25, 0, caja)
    cv2.rectangle(
        image, (x0, y0), (x0 + ancho_caja, y0 + alto_caja), (245, 117, 16), 2
    )

    texto_legible(image, "ELEGIR EJERCICIO", (x0 + 30, y0 + 45), 0.75)
    for i, (clave, ejercicio) in enumerate(EJERCICIOS.items(), start=1):
        actual = clave == clave_actual
        color = (0, 255, 0) if actual else (245, 245, 245)
        marca = ">" if actual else " "
        texto_legible(
            image,
            f"{marca} {i}   {ejercicio['nombre']}",
            (x0 + 30, y0 + 45 + i * 50),
            0.7,
            color,
        )
        texto_legible(
            image,
            ejercicio["vista"],
            (x0 + 75, y0 + 66 + i * 50),
            0.4,
            (150, 200, 230),
            1,
        )

    texto_legible(
        image,
        "numero = elegir     e = cerrar",
        (x0 + 30, y0 + alto_caja - 25),
        0.5,
        (200, 200, 200),
        1,
    )


def redactar_aviso(vis, ejercicio, angulo, calibrada):
    if not vis:
        return "No detecto a nadie en la imagen"

    extremos = (ejercicio["puntos"][0], ejercicio["puntos"][2])
    flojos = [NOMBRES[p] for p in extremos if vis[p] < UMBRAL_VISIBILIDAD]
    if flojos:
        return "No veo bien " + " ni ".join(flojos)
    if angulo is None:
        return "No puedo ubicar " + NOMBRES[ejercicio["puntos"][1]] + " con seguridad"
    if not calibrada:
        return "Calibrando: hace una repeticion completa y lenta"
    return None


def main():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUCION[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUCION[1])

    if not cap.isOpened():
        print("No se pudo abrir la camara.")
        return

    try:
        landmarker = cargar_landmarker()
    except RuntimeError as error:
        print(error)
        cap.release()
        return

    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    suave = Suavizador(FILTRO_CORTE, FILTRO_BETA)

    clave = EJERCICIO
    ejercicio = EJERCICIOS[clave]
    maquina = MaquinaRepeticiones(ejercicio)

    menu = False
    lado = None
    rango = [None, None]
    longitudes = deque(maxlen=60)
    fallos = 0
    ultimo_ms = -1
    t0 = time.perf_counter()

    while True:
        ret, frame = cap.read()
        if not ret:
            fallos += 1
            if fallos > 30:
                print("Se perdio la conexion con la camara.")
                break
            continue
        fallos = 0

        if ESPEJO:
            frame = cv2.flip(frame, 1)
        if MEJORAR_CONTRASTE:
            frame = mejorar_contraste(frame, clahe)

        ahora = time.perf_counter() - t0
        ultimo_ms = max(int(ahora * 1000), ultimo_ms + 1)

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        resultados = landmarker.detect_for_video(mp_image, ultimo_ms)

        alto, ancho = frame.shape[:2]
        angulo = None
        vis = {}
        vertice_px = None

        if resultados.pose_landmarks and resultados.pose_world_landmarks:
            landmarks = resultados.pose_landmarks[0]
            mundo = resultados.pose_world_landmarks[0]

            anterior, lado = lado, elegir_lado(landmarks, lado, ejercicio)
            if lado != anterior and anterior is not None:
                longitudes.clear()
            grupos = PUNTOS[lado]

            nombres = ejercicio["puntos"]
            vis = {p: confianza_grupo(landmarks, grupos[p]) for p in nombres}
            extremos_ok = all(
                vis[p] >= UMBRAL_VISIBILIDAD for p in (nombres[0], nombres[2])
            )

            if extremos_ok:
                medidos = [
                    punto_grupo(mundo, landmarks, grupos[p]) for p in nombres
                ]
                if all(p is not None for p in medidos):
                    a, b, c = (
                        suave(p, v, ahora) for p, v in zip(nombres, medidos)
                    )
                    valido, medidas = longitudes_plausibles(a, b, c, longitudes)
                    if valido:
                        longitudes.append(medidas)
                        angulo = calcular_angulo(a, b, c)

            puntos_px = []
            for i, lm in enumerate(landmarks):
                x, y = suave(i, [lm.x, lm.y], ahora) * [ancho, alto]
                puntos_px.append((int(x), int(y)))
            visibles = [confianza(lm) >= UMBRAL_VISIBILIDAD for lm in landmarks]

            destacados = set()
            for orden, p in enumerate(nombres):
                principal = grupos[p][0]
                destacados.add(principal)
                if orden == 1:
                    visibles[principal] = angulo is not None
                else:
                    visibles[principal] = vis[p] >= UMBRAL_VISIBILIDAD

            vertice_px = puntos_px[grupos[nombres[1]][0]]
            dibujar_esqueleto(
                image=frame,
                puntos_px=puntos_px,
                visibles=visibles,
                destacados=destacados,
            )

        if angulo is not None and not menu:
            rango[0] = angulo if rango[0] is None else min(rango[0], angulo)
            rango[1] = angulo if rango[1] is None else max(rango[1], angulo)
            antes = maquina.contador
            maquina.actualizar(angulo, ahora)
            if maquina.contador != antes:
                print(f"{ejercicio['nombre']}: {maquina.contador}")

        if angulo is not None and vertice_px is not None:
            x, y = vertice_px
            texto_legible(frame, f"{int(angulo)}", (x + 18, y - 14))

        if menu:
            dibujar_menu(frame, clave)
        else:
            dibujar_panel(
                frame,
                maquina.contador,
                maquina.estado,
                redactar_aviso(vis, ejercicio, angulo, maquina.umbrales is not None),
                ejercicio,
            )
        cv2.imshow(VENTANA, frame)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:
            break
        if tecla == ord("e"):
            menu = not menu
        if menu and ord("1") <= tecla <= ord("9"):
            claves = list(EJERCICIOS)
            elegida = tecla - ord("1")
            if elegida < len(claves):
                clave = claves[elegida]
                ejercicio = EJERCICIOS[clave]
                maquina = MaquinaRepeticiones(ejercicio)
                suave.reiniciar()
                longitudes.clear()
                rango = [None, None]
                lado = None
                menu = False
        if tecla == ord("r"):
            maquina.reiniciar()
            suave.reiniciar()
            longitudes.clear()
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

    cap.release()
    cv2.destroyAllWindows()
    landmarker.close()


if __name__ == "__main__":
    main()
