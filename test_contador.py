"""Pruebas de la logica de medicion y conteo.

Se ejecutan con:  python -m unittest -v

No requieren camara ni dependencias adicionales: todas las funciones bajo
prueba son puras. La documentacion de cada decision esta en docs/DISENO.md.
"""

import contextlib
import io
import json
import math
import os
import tempfile
import unittest
from collections import deque

import contador_repeticiones as m


class LandmarkFalso:
    """Imita un landmark de MediaPipe con los campos que el programa consulta."""

    __slots__ = ("x", "y", "z", "visibility", "presence")

    def __init__(self, visibility=0.9, presence=None, x=0.0, y=0.0, z=0.0):
        self.visibility = visibility
        self.presence = visibility if presence is None else presence
        self.x, self.y, self.z = x, y, z


def ruido(i):
    """Ruido determinista, identico en Python y en JavaScript."""
    x = math.sin(i * 12.9898) * 43758.5453
    return (x - math.floor(x) - 0.5) * 2


def senal(centro, amplitud, frecuencia=0.4, sigma=3.0, segundos=20, fps=30):
    return [
        centro
        + amplitud * math.cos(2 * math.pi * frecuencia * (i / fps))
        + sigma * ruido(i)
        for i in range(int(segundos * fps))
    ]


def contar(ejercicio, valores, fps=30):
    maquina = m.MaquinaRepeticiones(ejercicio)
    for i, valor in enumerate(valores):
        maquina.actualizar(valor, i / fps)
    return maquina.contador


class TestCalcularAngulo(unittest.TestCase):
    def test_angulos_conocidos_en_2d(self):
        self.assertAlmostEqual(m.calcular_angulo([0, 0], [0, 1], [1, 1]), 90.0)
        self.assertAlmostEqual(m.calcular_angulo([0, 0], [1, 0], [2, 0]), 180.0)
        self.assertAlmostEqual(m.calcular_angulo([1, 0], [0, 0], [1, 0]), 0.0)

    def test_funciona_igual_en_3d(self):
        self.assertAlmostEqual(m.calcular_angulo([1, 0, 0], [0, 0, 0], [0, 0, 1]), 90.0)

    def test_puntos_encimados_devuelve_none(self):
        self.assertIsNone(m.calcular_angulo([0, 0], [0, 0], [1, 1]))

    def test_puntos_alineados_no_rompe(self):
        """El clip evita que un redondeo deje el coseno fuera de [-1, 1]."""
        angulo = m.calcular_angulo([0, 0, 0], [1e-9, 0, 0], [2e-9, 0, 0])
        self.assertIsNotNone(angulo)
        self.assertTrue(0.0 <= angulo <= 180.0)

    def test_no_depende_de_la_escala(self):
        chico = m.calcular_angulo([0, 0], [0, 1], [1, 1])
        grande = m.calcular_angulo([0, 0], [0, 100], [100, 100])
        self.assertAlmostEqual(chico, grande)


class TestConfianza(unittest.TestCase):
    def test_toma_el_menor_de_los_dos_campos(self):
        self.assertAlmostEqual(m.confianza(LandmarkFalso(0.8, presence=0.3)), 0.3)

    def test_campos_en_none_no_rompen(self):
        """En Python, comparar None con un float lanza TypeError."""
        vacio = LandmarkFalso(visibility=None, presence=None)
        self.assertEqual(m.confianza(vacio), 1.0)

    def test_un_solo_campo_presente(self):
        self.assertAlmostEqual(m.confianza(LandmarkFalso(0.42, presence=None)), 0.42)

    def test_grupo_toma_el_mejor(self):
        lms = [LandmarkFalso(0.16), LandmarkFalso(0.82), LandmarkFalso(0.40)]
        self.assertAlmostEqual(m.confianza_grupo(lms, (0, 1, 2)), 0.82)


class TestPuntoGrupo(unittest.TestCase):
    def setUp(self):
        self.lms = [LandmarkFalso(0.9) for _ in range(33)]
        self.lms[16] = LandmarkFalso(0.16, x=0.30)
        self.lms[18] = LandmarkFalso(0.82, x=0.32)
        self.lms[20] = LandmarkFalso(0.75, x=0.33)
        self.lms[22] = LandmarkFalso(0.70, x=0.31)

    def test_pondera_por_confianza(self):
        """La muneca floja pesa poco; el resultado cae cerca de los dedos."""
        punto = m.punto_grupo(self.lms, self.lms, (16, 18, 20, 22))
        self.assertAlmostEqual(punto[0], 0.318889, places=5)

    def test_grupo_de_un_solo_landmark(self):
        solo = [LandmarkFalso(0.9, x=0.5)]
        self.assertAlmostEqual(m.punto_grupo(solo, solo, (0,))[0], 0.5)

    def test_todos_perdidos_devuelve_none(self):
        perdidos = [LandmarkFalso(0.01) for _ in range(4)]
        self.assertIsNone(m.punto_grupo(perdidos, perdidos, (0, 1, 2, 3)))


class TestLongitudesPlausibles(unittest.TestCase):
    def setUp(self):
        self.hombro = [0.0, 0.0, 0.0]
        self.codo = [0.30, 0.0, 0.0]
        self.mano = [0.30, 0.26, 0.0]
        self.historial = deque(maxlen=60)
        for _ in range(15):
            _, medidas = m.longitudes_plausibles(
                self.hombro, self.codo, self.mano, self.historial
            )
            self.historial.append(medidas)

    def test_acepta_sin_historial_suficiente(self):
        valido, _ = m.longitudes_plausibles(
            self.hombro, self.codo, self.mano, deque()
        )
        self.assertTrue(valido)

    def test_acepta_la_pose_calibrada(self):
        valido, _ = m.longitudes_plausibles(
            self.hombro, self.codo, self.mano, self.historial
        )
        self.assertTrue(valido)

    def test_acepta_ruido_normal(self):
        valido, _ = m.longitudes_plausibles(
            self.hombro, [0.33, 0.02, 0.0], self.mano, self.historial
        )
        self.assertTrue(valido)

    def test_rechaza_codo_alucinado_lejos(self):
        valido, _ = m.longitudes_plausibles(
            self.hombro, [0.70, 0.0, 0.0], self.mano, self.historial
        )
        self.assertFalse(valido)

    def test_rechaza_codo_colapsado_sobre_el_hombro(self):
        valido, _ = m.longitudes_plausibles(
            self.hombro, [0.05, 0.0, 0.0], self.mano, self.historial
        )
        self.assertFalse(valido)

    def test_rechaza_segmento_de_longitud_cero(self):
        valido, medidas = m.longitudes_plausibles(
            self.hombro, self.hombro, self.mano, self.historial
        )
        self.assertFalse(valido)
        self.assertIsNone(medidas)

    def test_la_mediana_ignora_un_frame_atipico(self):
        """Un valor absurdo no debe contaminar la referencia."""
        contaminado = deque(self.historial, maxlen=60)
        contaminado.append((2.0, 2.0))
        valido, _ = m.longitudes_plausibles(
            self.hombro, self.codo, self.mano, contaminado
        )
        self.assertTrue(valido)


class TestElegirLado(unittest.TestCase):
    def setUp(self):
        self.ejercicio = m.EJERCICIOS["curl"]
        self.lms = [LandmarkFalso(0.9) for _ in range(33)]

    def _debilitar(self, indices, valor=0.1):
        for i in indices:
            self.lms[i] = LandmarkFalso(valor)

    def test_respeta_el_lado_fijado_por_configuracion(self):
        original = m.LADO
        try:
            m.LADO = "izquierdo"
            self.assertEqual(m.elegir_lado(self.lms, None, self.ejercicio), "izquierdo")
        finally:
            m.LADO = original

    def test_elige_el_mejor_cuando_no_hay_lado_previo(self):
        self._debilitar((12, 16, 18, 20, 22))
        self.assertEqual(m.elegir_lado(self.lms, None, self.ejercicio), "izquierdo")

    def test_no_cambia_mientras_el_actual_sirva(self):
        """La eleccion es pegajosa: evita saltar de brazo a mitad de una serie."""
        self.assertEqual(
            m.elegir_lado(self.lms, "derecho", self.ejercicio), "derecho"
        )

    def test_cambia_cuando_el_actual_deja_de_servir(self):
        self._debilitar((12, 16, 18, 20, 22))
        self.assertEqual(
            m.elegir_lado(self.lms, "derecho", self.ejercicio), "izquierdo"
        )


class TestMaquinaRepeticiones(unittest.TestCase):
    def test_cuenta_los_cuatro_ejercicios(self):
        perfiles = {
            "curl": (105, 55),
            "sentadilla": (127, 48),
            "press": (125, 45),
            "elevacion": (50, 37),
        }
        for clave, (centro, amplitud) in perfiles.items():
            with self.subTest(ejercicio=clave):
                contadas = contar(m.EJERCICIOS[clave], senal(centro, amplitud))
                self.assertGreaterEqual(contadas, 7, "deberia contar 8 repeticiones")
                self.assertLessEqual(contadas, 8)

    def test_sin_historial_suficiente_no_calibra(self):
        """Hacen falta 30 muestras antes de intentar deducir el recorrido."""
        maquina = m.MaquinaRepeticiones(m.EJERCICIOS["curl"])
        for i, valor in enumerate(senal(105, 55)[:29]):
            maquina.actualizar(valor, i / 30)
        self.assertIsNone(maquina.umbrales)
        self.assertEqual(maquina.contador, 0)

    def test_recorrido_comprimido_igual_cuenta(self):
        """El caso que fallaba con umbrales fijos: el brazo llega solo a 82 grados."""
        self.assertGreaterEqual(contar(m.EJERCICIOS["curl"], senal(123, 41)), 7)

    def test_no_cuenta_con_recorrido_menor_al_minimo(self):
        self.assertEqual(contar(m.EJERCICIOS["curl"], senal(105, 20)), 0)

    def test_rechaza_ruido_sin_movimiento(self):
        """Con min/max en vez de percentiles, esto producia 27 falsas."""
        for sigma in (4, 8, 12, 20, 30):
            with self.subTest(sigma=sigma):
                quieto = [100 + sigma * ruido(i) for i in range(600)]
                self.assertEqual(contar(m.EJERCICIOS["curl"], quieto), 0)

    def test_cuenta_igual_a_distintas_velocidades(self):
        lento = contar(m.EJERCICIOS["curl"], senal(105, 55, frecuencia=0.15))
        self.assertGreaterEqual(lento, 2)
        rapido = contar(m.EJERCICIOS["curl"], senal(105, 55, frecuencia=0.8))
        self.assertGreaterEqual(rapido, 15)

    def test_contar_en_up_y_ciclo_usan_extremos_opuestos(self):
        valores = senal(105, 55)
        arriba = dict(m.EJERCICIOS["curl"], contar_en="up")
        ciclo = dict(m.EJERCICIOS["curl"], contar_en="ciclo")
        self.assertGreaterEqual(contar(arriba, valores), 7)
        self.assertGreaterEqual(contar(ciclo, valores), 7)

    def test_permanecer_flexionado_no_suma_de_nuevo(self):
        """Contado el cruce a 'up', quedarse ahi no agrega repeticiones."""
        maquina = m.MaquinaRepeticiones(m.EJERCICIOS["curl"])
        for i, valor in enumerate(senal(105, 55)):
            maquina.actualizar(valor, i / 30)

        # llevar el brazo a flexion y sostenerlo varios segundos
        for j in range(120):
            maquina.actualizar(50.0, (600 + j) / 30)
        self.assertEqual(maquina.estado, "up")
        contador = maquina.contador

        for j in range(120):
            maquina.actualizar(50.0, (720 + j) / 30)
        self.assertEqual(maquina.contador, contador)

    def test_antirrebote_por_duracion(self):
        """Dos cruces en menos de DURACION_MIN_REP cuentan una sola vez."""
        maquina = m.MaquinaRepeticiones(m.EJERCICIOS["curl"])
        for i, valor in enumerate(senal(105, 55, frecuencia=4.0)):
            maquina.actualizar(valor, i / 30)
        self.assertLessEqual(maquina.contador, 20 / m.DURACION_MIN_REP)

    def test_reiniciar_limpia_el_estado(self):
        maquina = m.MaquinaRepeticiones(m.EJERCICIOS["curl"])
        for i, valor in enumerate(senal(105, 55)):
            maquina.actualizar(valor, i / 30)
        self.assertGreater(maquina.contador, 0)

        maquina.reiniciar()
        self.assertEqual(maquina.contador, 0)
        self.assertIsNone(maquina.estado)
        self.assertIsNone(maquina.umbrales)

    def test_umbrales_dentro_del_recorrido(self):
        maquina = m.MaquinaRepeticiones(m.EJERCICIOS["curl"])
        for i, valor in enumerate(senal(105, 55)):
            maquina.actualizar(valor, i / 30)
        bajo, alto = maquina.recorrido
        flexionado, extendido = maquina.umbrales
        self.assertGreater(flexionado, bajo)
        self.assertLess(extendido, alto)
        margen = m.MARGEN_UMBRAL * (alto - bajo)
        self.assertAlmostEqual(flexionado, bajo + margen)


class TestRedactarAviso(unittest.TestCase):
    def setUp(self):
        self.ejercicio = m.EJERCICIOS["curl"]

    def test_sin_persona(self):
        aviso = m.redactar_aviso({}, self.ejercicio, None, False)
        self.assertIn("No detecto a nadie", aviso)

    def test_nombra_el_punto_flojo(self):
        vis = {"hombro": 0.99, "codo": 0.16, "muneca": 0.20}
        self.assertEqual(
            m.redactar_aviso(vis, self.ejercicio, None, False), "No veo bien la mano"
        )

    def test_enumera_varios_puntos_flojos(self):
        vis = {"hombro": 0.30, "codo": 0.9, "muneca": 0.20}
        self.assertEqual(
            m.redactar_aviso(vis, self.ejercicio, None, False),
            "No veo bien el hombro ni la mano",
        )

    def test_el_codo_se_deduce_por_descarte(self):
        """Extremos visibles pero sin angulo: fallo la validacion geometrica."""
        vis = {"hombro": 0.99, "codo": 0.16, "muneca": 0.72}
        self.assertIn("el codo", m.redactar_aviso(vis, self.ejercicio, None, False))

    def test_avisa_mientras_calibra(self):
        vis = {"hombro": 0.99, "codo": 0.9, "muneca": 0.72}
        self.assertIn("Calibrando", m.redactar_aviso(vis, self.ejercicio, 90.0, False))

    def test_sin_aviso_cuando_todo_esta_bien(self):
        vis = {"hombro": 0.99, "codo": 0.9, "muneca": 0.72}
        self.assertIsNone(m.redactar_aviso(vis, self.ejercicio, 90.0, True))

    def test_usa_los_nombres_del_ejercicio_activo(self):
        vis = {"cadera": 0.9, "rodilla": 0.9, "tobillo": 0.2}
        aviso = m.redactar_aviso(vis, m.EJERCICIOS["sentadilla"], None, False)
        self.assertEqual(aviso, "No veo bien el pie")


class TestDescargarModelo(unittest.TestCase):
    """La descarga tiene que ser atomica: un archivo truncado en disco hace
    que el programa intente cargar un modelo corrupto en cada ejecucion."""

    def setUp(self):
        self.carpeta = tempfile.mkdtemp()
        self.destino = os.path.join(self.carpeta, "modelo.task")

    def _descargar(self, url):
        """Silencia el aviso de descarga para no ensuciar la salida."""
        with contextlib.redirect_stdout(io.StringIO()):
            m.descargar_modelo(self.destino, url)

    def test_url_inaccesible_no_deja_archivo(self):
        with self.assertRaises(RuntimeError):
            self._descargar("http://127.0.0.1:1/no-existe.task")
        self.assertFalse(os.path.exists(self.destino))
        self.assertFalse(os.path.exists(self.destino + ".parcial"))

    def test_descarga_truncada_no_deja_archivo(self):
        origen = os.path.join(self.carpeta, "chico.task")
        with open(origen, "wb") as archivo:
            archivo.write(b"no es un modelo")

        with self.assertRaises(RuntimeError):
            self._descargar("file:///" + origen.replace("\\", "/"))
        self.assertFalse(os.path.exists(self.destino))
        self.assertFalse(os.path.exists(self.destino + ".parcial"))

    def test_descarga_valida_deja_el_archivo(self):
        origen = os.path.join(self.carpeta, "grande.task")
        with open(origen, "wb") as archivo:
            archivo.write(b"x" * (m.TAMANO_MINIMO_MODELO + 1))

        self._descargar("file:///" + origen.replace("\\", "/"))
        self.assertTrue(os.path.exists(self.destino))
        self.assertFalse(os.path.exists(self.destino + ".parcial"))


class TestCasosCompartidos(unittest.TestCase):
    """Los mismos casos que verifica la version web, para detectar si las dos
    implementaciones se separan. Ver docs/WEB.md."""

    ARCHIVO = os.path.join("tests", "casos_compartidos.json")

    def test_python_reproduce_los_casos(self):
        with open(self.ARCHIVO, encoding="utf-8") as archivo:
            casos = json.load(archivo)

        for caso in casos["angulos"]:
            with self.subTest(caso=caso["nombre"]):
                obtenido = m.calcular_angulo(*caso["puntos"])
                self.assertAlmostEqual(obtenido, caso["esperado"], places=6)

        for caso in casos["conteos"]:
            with self.subTest(caso=caso["nombre"]):
                valores = senal(
                    caso["centro"], caso["amplitud"], sigma=caso["sigma"]
                )
                obtenido = contar(m.EJERCICIOS[caso["ejercicio"]], valores)
                self.assertEqual(obtenido, caso["esperado"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
