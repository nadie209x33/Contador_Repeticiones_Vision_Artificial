# La versión web

El proyecto incluye, además del programa de escritorio, una versión que se
ejecuta en el navegador, ubicada en la carpeta `web/`. Permite utilizar la
aplicación desde un dispositivo móvil o distribuirla mediante un enlace, sin
requerir ninguna instalación.

El procesamiento ocurre íntegramente en el dispositivo del usuario: el video no
se transmite a ningún servidor. Por ese motivo resulta suficiente un alojamiento
estático como Cloudflare Pages.

---

## Archivos

| Archivo | Contenido |
|---------|-----------|
| `web/index.html` | Estructura de la página |
| `web/styles.css` | Estilos |
| `web/logica.js` | Lógica de medición y conteo, sin componentes de interfaz |
| `web/app.js` | Cámara, dibujo en canvas y gestión de eventos |

La separación entre `logica.js` y `app.js` responde a un criterio funcional:
permite ejecutar y verificar la lógica de forma aislada, sin necesidad de cámara.
Ese aislamiento fue el que hizo posible validar la equivalencia del port.

---

## Ejecución local

Los módulos de JavaScript no se cargan al abrir el archivo directamente desde el
sistema de archivos: es necesario servirlos por HTTP. Desde la carpeta `web/`:

```bash
python -m http.server 8000
```

El sitio queda disponible en `http://localhost:8000`. El acceso a la cámara
funciona en `localhost` sin HTTPS; en cualquier otro dominio, el navegador lo
bloquea si la conexión no es segura.

---

## Publicación en Cloudflare Pages

### 1. Incorporar la carpeta al repositorio

Cloudflare obtiene el proyecto desde GitHub, de modo que la carpeta `web/` debe
estar publicada en el repositorio.

### 2. Crear el proyecto

En el panel de Cloudflare: **Workers & Pages** → **Create** → **Pages** →
**Connect to Git**. Se autoriza el acceso al repositorio y se lo selecciona de la
lista.

### 3. Configurar la compilación

| Campo | Valor |
|-------|-------|
| Framework preset | None |
| Build command | *(vacío)* |
| Build output directory | `web` |

El último campo determina que el contenido de `web/` se publique como raíz del
sitio. Si se omite, la página queda accesible en `dominio.pages.dev/web/` en
lugar de la raíz.

No se especifica comando de compilación porque el proyecto no requiere ninguna:
se trata de archivos estáticos.

### 4. Desplegar

La opción **Save and Deploy** genera el sitio en aproximadamente un minuto y
devuelve una URL con el formato `nombre-del-proyecto.pages.dev`, con HTTPS
incluido. El certificado es un requisito, ya que los navegadores condicionan el
acceso a la cámara a una conexión segura.

Cada push a la rama `main` dispara un nuevo despliegue automáticamente.

---

## Diferencias respecto del programa de escritorio

### Componentes equivalentes

La lógica se trasladó de forma literal y produce resultados idénticos. La
equivalencia se verificó ejecutando los mismos escenarios en ambos lenguajes:

| Prueba | Python | JavaScript |
|--------|--------|------------|
| Ángulos conocidos (2D y 3D) | 90 / 180 / 90 | 90 / 180 / 90 |
| Percentiles y medianas | 5.95 / 95.05 / 50.5 | 5.95 / 95.05 / 50.5 |
| Punto de grupo ponderado | 0.318889 | 0.318889 |
| Conteo en los cuatro ejercicios | 7 / 7 / 8 / 8 | 7 / 7 / 8 / 8 |
| Rechazo de ruido (σ de 4 a 30) | 0 falsas | 0 falsas |
| Recorridos cortos | 7 / 3 / 0 | 7 / 3 / 0 |

Los once escenarios coinciden de forma exacta.

### Componentes sustituidos

| Escritorio | Web |
|------------|-----|
| `cv2.VideoCapture` | `getUserMedia` |
| Dibujo mediante `cv2` | Canvas 2D |
| Panel y menú dibujados sobre la imagen | Elementos HTML |
| `np.percentile`, `np.median` | Implementación propia |

La construcción del panel con elementos HTML presenta una ventaja adicional: el
texto se renderiza de forma nítida en cualquier resolución y queda eliminado el
problema del ancho variable de los glifos, que en la versión de escritorio
producía carteles duplicados.

### Funcionalidad no trasladada

La ecualización adaptativa de histograma (CLAHE) no tiene equivalente en el
navegador. Se la sustituyó por un filtro de canvas
(`contrast(1.25) brightness(1.08)`), que aplica un ajuste global en lugar de una
ecualización por zonas, por lo que resulta menos efectivo frente al contraluz.

Una implementación equivalente sería posible operando directamente sobre los
píxeles del canvas, o mediante un shader en WebGL. No se realizó debido a que el
costo en complejidad es elevado y una iluminación frontal adecuada resuelve el
problema en su origen.

---

## Detalles de implementación

**Espejado.** La detección se ejecuta sobre la imagen sin espejar, de manera que
los landmarks conservan sus coordenadas originales y la correspondencia
anatómica de los lados se mantiene. El espejado es exclusivamente visual: al
dibujar se emplea `1 - x`.

**Marcas de tiempo.** `detectForVideo` requiere valores estrictamente crecientes,
al igual que en la versión de Python, y se resuelve del mismo modo mediante
`Math.max(actual, ultimo + 1)`.

**Frames repetidos.** El bucle se ejecuta con `requestAnimationFrame`, que
habitualmente opera a 60 Hz mientras la cámara entrega 30 cuadros por segundo.
Para evitar procesar dos veces la misma imagen, se compara `video.currentTime`
con el valor anterior y se omite el frame si no ha variado.

**Modelo.** Se descarga desde el CDN de Google (9 MB, con CORS habilitado).
También podría alojarse junto al sitio en Cloudflare, dado que el límite de
Pages es de 25 MB por archivo, pero la carga desde el CDN permite aprovechar la
caché del navegador si el usuario ya accedió a otra página que utilice el mismo
modelo.
