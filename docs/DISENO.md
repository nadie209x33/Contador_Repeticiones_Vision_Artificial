# Cómo funciona y por qué

Las decisiones de diseño del programa, explicadas. Para el uso, ver
[README.md](README.md); para el código línea por línea, [CODIGO.md](CODIGO.md).

---

## El flujo

```
Webcam → realce de contraste → MediaPipe → 33 puntos del cuerpo
       → suavizado → ángulo del codo → contador
```

1. **Detectar.** MediaPipe ubica 33 puntos del cuerpo en cada frame.
2. **Suavizar.** Se filtran las coordenadas para que no tiemblen.
3. **Medir.** Se calcula el ángulo que forman hombro, codo y mano.
4. **Contar.** Cuando el ángulo cruza dos umbrales en orden, hay repetición.

> MediaPipe retiró la API vieja (`mp.solutions.pose`). Se usa la nueva,
> `PoseLandmarker`, que necesita descargar un archivo de modelo la primera vez.

El resto de este documento explica las cuatro decisiones que hicieron que esto
funcionara de verdad.

---

## 1. Dónde se mide el ángulo

MediaPipe devuelve cada punto en dos formatos, y elegir mal cuál usar era el
error más grave que tenía el programa.

| | Coordenadas de imagen | Coordenadas del mundo |
|---|---|---|
| Unidad | Fracción del frame (0 a 1) | Metros |
| Origen | Esquina de la imagen | Cadera de la persona |
| Sirve para | **Dibujar** | **Medir** |

### El problema

En las coordenadas de imagen, `x` está dividido por el ancho e `y` por el alto.
Como el frame no es cuadrado, **el mismo movimiento da números distintos según la
dirección**.

> En un frame de 640×480, moverse 10 píxeles a la derecha suma 0.0156 a `x`, pero
> 10 píxeles hacia abajo suma 0.0208 a `y`. Es como medir el ancho en metros y el
> alto en yardas: podés dibujar bien, pero cualquier ángulo que calcules va a
> estar torcido.

Medido sobre 640×480, el error llega a **16°**: un codo que en realidad está a
100° se lee como 83.6°. Con un umbral en 55°, esa deriva alcanza para que una
repetición válida nunca lo cruce.

### La solución

El ángulo se calcula sobre las coordenadas del mundo, que están en metros en las
tres direcciones. No dependen de la forma del frame, y al ser 3D también corrigen
el achatamiento que aparece cuando el brazo no está de frente a la cámara.

Las de imagen se siguen usando para dibujar, porque las del mundo tienen origen
en la cadera y no se pueden traducir a píxeles.

---

## 2. Cuándo se confía en un punto

MediaPipe entrega un número de confianza por punto, de 0 a 1. **Ese número no es
confiable**: baja a 0.1–0.2 en articulaciones que se ven perfectamente. Pasó con
la muñeca (0.16 con el brazo despejado) y con el codo. Si se lo usa como reja
rígida, el programa descarta mediciones correctas y deja de contar.

Por eso cada punto se valida de una forma distinta.

### El hombro y la mano: por confianza

Son los dos puntos donde el número sí es razonable. Se les exige superar
`UMBRAL_VISIBILIDAD`.

Además, **la mano no es la muñeca**. Se promedian cuatro puntos —muñeca, meñique,
índice y pulgar— dándole más peso a los que se ven mejor.

> Si la muñeca tiene confianza 0.16 pero el meñique 0.82, el promedio cae casi
> encima del meñique. Como los cuatro están sobre la misma línea del antebrazo,
> el ángulo casi no cambia, pero ahora sí hay medición. En el caso real, la
> confianza pasó de **0.16 a 0.82**.

### El codo: por geometría

El codo es el vértice del ángulo, el punto que más importa, y es donde la
confianza falla más. Así que se lo valida con física en lugar del score.

Brazo y antebrazo son huesos: **su largo no cambia**, aunque la persona se mueva o
se acerque a la cámara. Si el modelo se inventa el codo, ese largo se dispara.

El programa se guarda la **mediana** de las últimas 60 mediciones y rechaza el
frame si alguna se desvía más de `TOLERANCIA_LONGITUD`.

> ¿Por qué la mediana y no el promedio? Si medís el brazo cinco veces y obtenés
> 0.30, 0.31, 0.29, 0.30 y 0.85 metros, el promedio da 0.41 —arruinado por el
> error—, pero la mediana da 0.30. La mediana ignora los valores raros por
> definición, así que un frame malo no contamina la referencia.

---

## 3. Cuándo cuenta como repetición

### Los umbrales fijos no funcionan

El ángulo medido tiene sesgos que dependen de la postura, la distancia y el
ángulo de la cámara. Un brazo bien flexionado puede leerse como 82° en vez de
40°.

Con un umbral fijo en 55°, ese movimiento queda rozando el límite: a veces lo
cruza y a veces no. Ese era exactamente el síntoma de "a veces cuenta y a veces
no".

### Los umbrales se calibran solos

El programa guarda los últimos 10 segundos de ángulo y saca los umbrales del
recorrido que la persona hace **en realidad**:

```
recorrido         = percentil 95 − percentil 5
umbral flexionado = percentil 5  + MARGEN_UMBRAL · recorrido
umbral extendido  = percentil 95 − MARGEN_UMBRAL · recorrido
```

> **Qué es un percentil.** Si ordenás 100 mediciones de menor a mayor, el
> percentil 5 es la que quedó en la posición 5 y el percentil 95 la que quedó en
> la 95. O sea: casi el mínimo y casi el máximo, pero descartando los extremos.
>
> Con un recorrido de 82° a 165° y `MARGEN_UMBRAL = 0.15`, los umbrales quedan en
> 95° y 152°.

**Por qué percentiles y no el mínimo y el máximo.** Los extremos crudos recogen el
ruido: un brazo quieto con puntos temblorosos abarca un rango amplio sin haberse
movido. Probado con `min`/`max`, un brazo inmóvil producía **27 repeticiones
fantasma**.

**Dos controles antes de aplicar la calibración:**

- El recorrido tiene que superar `AMPLITUD_MINIMA`, para no contar movimientos
  mínimos.
- La señal tiene que ser **suave**. Una repetición es un movimiento lento; el
  ruido salta de un frame al siguiente. Si el cambio típico entre frames es
  grande comparado con el recorrido total, eso es temblor, no ejercicio.

> Un curl real cambia unos 2° por frame y recorre 88°. Puro ruido cambia 19° por
> frame y "recorre" 66°. El recorrido se parece; la suavidad los separa.

Si algo falla, se vuelve a los umbrales fijos. En la práctica, **la primera
repetición sirve de calibración**.

### Cuánto hay que completar del movimiento

`MARGEN_UMBRAL` define qué tan adentro del recorrido quedan los umbrales:

| Valor | Se cuenta al completar |
|-------|------------------------|
| 0.25 | 75% del recorrido |
| **0.15** | **85% del recorrido** |
| 0.10 | 90% del recorrido |

### Histéresis

Entre los dos umbrales hay una zona muerta donde el estado no cambia.

> Es lo mismo que hace un termostato: si prende a 19° y apaga a 21°, no está
> encendiéndose y apagándose todo el tiempo alrededor de los 20°. Con un solo
> umbral, el ruido dispararía varios conteos en un mismo movimiento.

Además la repetición se cuenta en la **transición**, no mientras el estado se
mantiene. Por eso hay que extender el brazo antes de que la próxima subida valga.

### Resultados

Sobre 20 segundos simulados a 30 FPS:

| Escenario | Reales | Contadas |
|-----------|-------:|---------:|
| Recorrido comprimido (82–165°) | 8 | 8 |
| Recorrido completo (30–175°) | 8 | 8 |
| Con ruido fuerte | 8 | 8 |
| Movimiento parcial | 0 | 0 |
| Brazo quieto con temblor | 0 | 0 |

---

## 4. Cómo se estabiliza la imagen

### Filtro 1-euro

Un promedio móvil tiene un límite: si lo ajustás para que no tiemble, mete
retardo y el ángulo llega tarde al umbral; si lo aflojás, vuelve el temblor. No
hay punto medio que arregle las dos cosas.

El filtro **1-euro** cambia cuánto suaviza según la velocidad del punto:

```
corte = FILTRO_CORTE + FILTRO_BETA · velocidad
```

> Es como un amigo que te corrige la puntería: si estás quieto te sostiene la
> mano con firmeza, pero si movés el brazo rápido te suelta para no frenarte.

Se aplica a cada coordenada, no al ángulo final, y también a los píxeles para que
los marcadores no bailen.

Medido sobre un curl simulado con 1.5 cm de ruido por punto:

| | Temblor entre frames | Error contra el ángulo real |
|---|---:|---:|
| Sin filtrar | 9.75° | 4.65° |
| Promedio móvil | 5.80° | 7.51° |
| **1-euro** | **6.43°** | **3.39°** |

El promedio móvil bajaba el temblor pero empeoraba la exactitud: eso es el
retardo. El 1-euro mejora las dos cosas a la vez.

### Realce de contraste (CLAHE)

Con una ventana detrás, la cámara ajusta la exposición para la ventana y el
cuerpo queda como una mancha oscura, sin los bordes ni la textura que el detector
necesita.

CLAHE realza el contraste **por zonas** y solo sobre el brillo, así que aclara las
sombras sin quemar lo que ya estaba claro ni cambiar los colores. Duplica el
detalle disponible en la zona oscura.

Dos advertencias:

- **No reemplaza a la luz de frente.** Recupera detalle que estaba comprimido, no
  inventa el que la cámara nunca capturó.
- **Cuesta 15.6 ms por frame** a 720p. Si el programa va lento, es lo primero que
  conviene apagar.

---

## Otros detalles

- **Timestamps reales.** MediaPipe usa el tiempo entre frames para seguir a la
  persona. Sumar 33 ms fijos por frame lo desincroniza y los puntos llegan tarde,
  así que se usa el reloj real.
- **Elección de brazo pegajosa.** Recalcular el brazo activo en cada frame lo hace
  saltar entre uno y otro y rompe el conteo a mitad de repetición. Solo se cambia
  si el actual deja de servir.
- **Texto en pantalla.** En OpenCV el ancho de las letras depende del grosor del
  trazo. Dibujar el contorno más grueso que el relleno desfasa las dos pasadas y
  el texto se ve doble, así que todas usan el mismo grosor.
- **Tolerancia a fallos de cámara.** Una webcam USB puede fallar una lectura sin
  estar desconectada; el programa admite hasta 30 seguidas antes de rendirse.

---

## Parámetros

| Parámetro | Valor | Qué controla |
|-----------|-------|--------------|
| `LADO` | `"auto"` | Brazo a medir |
| `MODELO` | `"full"` | `lite` / `full` / `heavy` |
| `ESPEJO` | `True` | Imagen espejada |
| `MEJORAR_CONTRASTE` | `True` | Realce CLAHE |
| `DURACION_MIN_REP` | `0.5` | Segundos mínimos entre repeticiones |
| `CALIBRACION_AUTOMATICA` | `True` | Umbrales según el recorrido real |
| `MARGEN_UMBRAL` | `0.15` | Cuánto del recorrido hay que completar |
| `RUIDO_MAXIMO` | `0.15` | Cambio por frame admitido |
| `VENTANA_CALIBRACION` | `300` | Frames de historial (≈10 s) |
| `EJERCICIO` | `"curl"` | Ejercicio inicial |
| `UMBRAL_VISIBILIDAD` | `0.5` | Confianza mínima de los dos puntos externos |
| `TOLERANCIA_LONGITUD` | `0.4` | Desvío máximo de brazo y antebrazo |
| `FILTRO_CORTE` | `1.0` | Suavizado en reposo |
| `FILTRO_BETA` | `10.0` | Respuesta al movimiento rápido |

---

## Diagnóstico

La tecla `d` imprime por consola el brazo activo, el ángulo, el rango observado,
los umbrales vigentes y la confianza de cada punto.

| Lo que ves | Qué significa | Qué hacer |
|------------|---------------|-----------|
| *No veo bien...* | Uno de los dos puntos externos no llega a `UMBRAL_VISIBILIDAD` | Luz de frente, entrar entero en cuadro |
| *No puedo ubicar... con seguridad* | El vértice no pasó la validación geométrica | Mostrar el miembro entero; si sigue, subir `TOLERANCIA_LONGITUD` |
| *No detecto a nadie en la imagen* | No se encontró ninguna persona | Alejarse, mejorar la luz |
| `umbrales=... (fijos)` | La calibración no se activó | Hacer el movimiento completo |
| Todo bien pero no cuenta | El brazo nunca pasó por `down` | Extender el brazo antes de la próxima subida |

---

## Ejercicios

Cada ejercicio es una entrada del diccionario `EJERCICIOS`: tres articulaciones,
en qué extremo se cuenta y sus propios umbrales. La lógica no cambia.

| Ejercicio | Puntos (el del medio es el vértice) | Cuenta en | Vista | Recorrido |
|-----------|--------------------------------------|-----------|-------|-----------|
| Curl de bíceps | hombro – **codo** – muñeca | `up` | de perfil | 50–160° |
| Press de hombros | hombro – **codo** – muñeca | `ciclo` | de frente | 80–170° |
| Elevación lateral | cadera – **hombro** – codo | `ciclo` | de frente | 10–90° |
| Sentadilla | cadera – **rodilla** – tobillo | `up` | de perfil | 70–170° |

### Cada ejercicio necesita su propia orientación de cámara

MediaPipe estima la profundidad (`z`) mucho peor que el ancho y el alto: la
deduce de las proporciones del cuerpo, no la mide. Un movimiento que va y viene
**hacia la cámara** cae justo sobre ese eje y se mide comprimido.

El curl y la sentadilla ocurren en el plano lateral del cuerpo: hay que ponerse
de perfil para que el movimiento quede a lo ancho de la imagen. El press y la
elevación ocurren en el plano frontal: hay que ponerse de frente.

Si la orientación es la equivocada, el recorrido medido se achica y puede quedar
por debajo de `amplitud_min`, y entonces el programa no cuenta nada. Por eso cada
ejercicio lleva un campo `vista` que se muestra en pantalla y en el menú.

### Por qué "cuenta en" resuelve las dos direcciones

La máquina de estados llama `up` al ángulo chico y `down` al grande. En el curl
la repetición se completa al doblar el brazo, o sea con el ángulo chico:
`contar_en = "up"`.

En el press y en la elevación lateral es al revés: la repetición se completa al
estirar, con el ángulo grande. Eso es `contar_en = "ciclo"`, que cuenta la
transición contraria. No hizo falta lógica nueva.

### Cada ejercicio necesita sus propios parámetros

No alcanza con cambiar las tres articulaciones. `amplitud_min` estaba calibrado
para el curl, que recorre unos 110°. La elevación lateral recorre 80° y el puente
de glúteos apenas 60°: con el valor del curl, la calibración nunca se activa y el
contador queda en cero.

Por eso `amplitud_min`, `contar_en` y los umbrales de respaldo viven adentro de
cada ejercicio, y no como constantes globales.

### Grupos de puntos

Un "punto" del ejercicio puede ser varios landmarks promediados. La muñeca en
realidad es muñeca + meñique + índice + pulgar, y el tobillo es tobillo + talón +
punta del pie, porque ambos sufren el mismo problema de confianza mal reportada.
Las articulaciones que sí se reportan bien —hombro, codo, cadera, rodilla— son
grupos de un solo elemento.

### Qué falta para otros ejercicios

Las flexiones de brazos miden bien el ángulo del codo, pero desde una webcam de
escritorio quedás en el piso y los puntos se autoocluyen. Los jumping jacks y los
burpees no son un solo ángulo: necesitan combinar dos señales, o sea otra máquina
de estados.

---

## El menú

Se abre con `e` y se dibuja sobre la misma imagen de OpenCV: una tarjeta centrada
con el fondo atenuado, la lista numerada y el ejercicio actual en verde.

Mientras está abierto **el conteo se pausa**, para no sumar repeticiones mientras
elegís. La detección sigue corriendo, así que al cerrarlo no hay que esperar a
que el modelo vuelva a encontrarte.

Al cambiar de ejercicio se reinician el contador, la calibración, los filtros y
la referencia de longitudes: todo eso era del ejercicio anterior.
