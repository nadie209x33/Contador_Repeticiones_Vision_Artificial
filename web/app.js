import {
  FilesetResolver,
  PoseLandmarker,
} from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/vision_bundle.mjs";

import {
  CONEXIONES,
  EJERCICIOS,
  FILTRO_BETA,
  FILTRO_CORTE,
  MaquinaRepeticiones,
  PUNTOS,
  Suavizador,
  UMBRAL_VISIBILIDAD,
  calcularAngulo,
  confianza,
  confianzaGrupo,
  elegirLado,
  longitudesPlausibles,
  puntoGrupo,
  redactarAviso,
} from "./logica.js";

const WASM_BASE =
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm";
const MODELO_URL =
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/" +
  "pose_landmarker_full/float16/latest/pose_landmarker_full.task";

const EJERCICIO_INICIAL = "curl";
const ESPEJO = true;
const MEJORAR_CONTRASTE = true;

const video = document.getElementById("video");
const lienzo = document.getElementById("lienzo");
const ctx = lienzo.getContext("2d");
const oculto = document.createElement("canvas");
const ctxOculto = oculto.getContext("2d");

const ui = {
  panel: document.getElementById("panel"),
  controles: document.getElementById("controles"),
  contador: document.getElementById("contador"),
  estado: document.getElementById("estado"),
  ejercicio: document.getElementById("ejercicio-activo"),
  vista: document.getElementById("vista"),
  aviso: document.getElementById("aviso"),
  portada: document.getElementById("portada"),
  carga: document.getElementById("estado-carga"),
  menu: document.getElementById("menu"),
  lista: document.getElementById("lista-ejercicios"),
};

let landmarker = null;
let clave = EJERCICIO_INICIAL;
let ejercicio = EJERCICIOS[clave];
let maquina = new MaquinaRepeticiones(ejercicio);
const suave = new Suavizador(FILTRO_CORTE, FILTRO_BETA);
let lado = null;
let longitudes = [];
let menuAbierto = false;
let ultimoTiempoVideo = -1;
let ultimoMs = -1;
let t0 = 0;

function reiniciarMedicion() {
  maquina.reiniciar();
  suave.reiniciar();
  longitudes = [];
  lado = null;
}

function cambiarEjercicio(nueva) {
  clave = nueva;
  ejercicio = EJERCICIOS[clave];
  maquina = new MaquinaRepeticiones(ejercicio);
  suave.reiniciar();
  longitudes = [];
  lado = null;
  ui.ejercicio.textContent = ejercicio.nombre;
  ui.vista.textContent = "ponete " + ejercicio.vista;
  dibujarLista();
}

function dibujarLista() {
  ui.lista.innerHTML = "";
  Object.entries(EJERCICIOS).forEach(([id, ej], i) => {
    const boton = document.createElement("button");
    boton.type = "button";
    boton.className = id === clave ? "activo" : "";
    boton.innerHTML =
      `<span class="numero">${i + 1}</span>` +
      `<span><strong>${ej.nombre}</strong>` +
      `<span class="como">${ej.vista}</span></span>`;
    boton.addEventListener("click", () => {
      cambiarEjercicio(id);
      alternarMenu(false);
    });
    const li = document.createElement("li");
    li.appendChild(boton);
    ui.lista.appendChild(li);
  });
}

function alternarMenu(abrir) {
  menuAbierto = abrir ?? !menuAbierto;
  ui.menu.hidden = !menuAbierto;
}

function dibujarEsqueleto(landmarks, visibles, destacados, ancho, alto) {
  const px = landmarks.map((lm) => [
    (ESPEJO ? 1 - lm.x : lm.x) * ancho,
    lm.y * alto,
  ]);

  ctx.lineWidth = 3;
  ctx.strokeStyle = "#4275f5";
  for (const [a, b] of CONEXIONES) {
    if (!visibles[a] || !visibles[b]) continue;
    ctx.beginPath();
    ctx.moveTo(px[a][0], px[a][1]);
    ctx.lineTo(px[b][0], px[b][1]);
    ctx.stroke();
  }

  px.forEach(([x, y], i) => {
    if (destacados.has(i)) {
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fillStyle = visibles[i] ? "#22c55e" : "#ff3030";
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = "#ffffff";
      ctx.stroke();
    } else if (visibles[i]) {
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fillStyle = "#e642c6";
      ctx.fill();
    }
  });

  return px;
}

function escribirAngulo(angulo, punto) {
  const texto = String(Math.round(angulo));
  const x = punto[0] + 18;
  const y = punto[1] - 14;
  ctx.font = "600 22px system-ui, sans-serif";
  ctx.lineJoin = "round";
  ctx.lineWidth = 6;
  ctx.strokeStyle = "#000";
  ctx.strokeText(texto, x, y);
  ctx.fillStyle = "#fff";
  ctx.fillText(texto, x, y);
}

function procesar(ahora) {
  const ancho = video.videoWidth;
  const alto = video.videoHeight;
  if (!ancho || !alto) return;

  if (lienzo.width !== ancho) {
    lienzo.width = ancho;
    lienzo.height = alto;
    oculto.width = ancho;
    oculto.height = alto;
  }

  ctxOculto.filter = MEJORAR_CONTRASTE
    ? "contrast(1.25) brightness(1.08)"
    : "none";
  ctxOculto.drawImage(video, 0, 0, ancho, alto);

  ultimoMs = Math.max(Math.round(ahora * 1000), ultimoMs + 1);
  const resultado = landmarker.detectForVideo(oculto, ultimoMs);

  ctx.save();
  if (ESPEJO) {
    ctx.translate(ancho, 0);
    ctx.scale(-1, 1);
  }
  ctx.drawImage(oculto, 0, 0, ancho, alto);
  ctx.restore();

  let angulo = null;
  let vis = null;

  const landmarks = resultado.landmarks?.[0];
  const mundo = resultado.worldLandmarks?.[0];

  if (landmarks && mundo) {
    const anterior = lado;
    lado = elegirLado(landmarks, lado, ejercicio);
    if (lado !== anterior && anterior !== null) longitudes = [];
    const grupos = PUNTOS[lado];

    const nombres = ejercicio.puntos;
    vis = {};
    for (const p of nombres) vis[p] = confianzaGrupo(landmarks, grupos[p]);

    const extremosOk =
      vis[nombres[0]] >= UMBRAL_VISIBILIDAD &&
      vis[nombres[2]] >= UMBRAL_VISIBILIDAD;

    if (extremosOk) {
      const medidos = nombres.map((p) =>
        puntoGrupo(mundo, landmarks, grupos[p]),
      );
      if (medidos.every((p) => p !== null)) {
        const [a, b, c] = medidos.map((v, i) =>
          suave.aplicar(nombres[i], v, ahora),
        );
        const [valido, medidas] = longitudesPlausibles(a, b, c, longitudes);
        if (valido) {
          longitudes.push(medidas);
          if (longitudes.length > 60) longitudes.shift();
          angulo = calcularAngulo(a, b, c);
        }
      }
    }

    const visibles = landmarks.map((lm) => confianza(lm) >= UMBRAL_VISIBILIDAD);
    const destacados = new Set();
    nombres.forEach((p, orden) => {
      const principal = grupos[p][0];
      destacados.add(principal);
      visibles[principal] =
        orden === 1 ? angulo !== null : vis[p] >= UMBRAL_VISIBILIDAD;
    });

    const px = dibujarEsqueleto(landmarks, visibles, destacados, ancho, alto);
    if (angulo !== null) escribirAngulo(angulo, px[grupos[nombres[1]][0]]);
  }

  if (angulo !== null && !menuAbierto) maquina.actualizar(angulo, ahora);

  ui.contador.textContent = maquina.contador;
  ui.estado.textContent = maquina.estado ?? "-";
  const aviso = redactarAviso(vis, ejercicio, angulo, maquina.umbrales !== null);
  ui.aviso.textContent = aviso ?? "";
  ui.aviso.hidden = !aviso;
}

function bucle() {
  if (video.currentTime !== ultimoTiempoVideo) {
    ultimoTiempoVideo = video.currentTime;
    procesar((performance.now() - t0) / 1000);
  }
  requestAnimationFrame(bucle);
}

async function empezar() {
  const boton = document.getElementById("btn-empezar");
  boton.disabled = true;

  try {
    ui.carga.textContent = "Cargando el modelo de pose (unos 9 MB)...";
    const vision = await FilesetResolver.forVisionTasks(WASM_BASE);
    landmarker = await PoseLandmarker.createFromOptions(vision, {
      baseOptions: { modelAssetPath: MODELO_URL, delegate: "GPU" },
      runningMode: "VIDEO",
      numPoses: 1,
      minPoseDetectionConfidence: 0.6,
      minPosePresenceConfidence: 0.6,
      minTrackingConfidence: 0.6,
    });

    ui.carga.textContent = "Pidiendo acceso a la camara...";
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 1280 },
        height: { ideal: 720 },
        facingMode: "user",
      },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();

    ui.portada.hidden = true;
    ui.panel.hidden = false;
    ui.controles.hidden = false;
    t0 = performance.now();
    bucle();
  } catch (error) {
    boton.disabled = false;
    ui.carga.textContent = "No se pudo iniciar: " + error.message;
    console.error(error);
  }
}

document.getElementById("btn-empezar").addEventListener("click", empezar);
document
  .getElementById("btn-menu")
  .addEventListener("click", () => alternarMenu());
document
  .getElementById("btn-cerrar")
  .addEventListener("click", () => alternarMenu(false));
document
  .getElementById("btn-reiniciar")
  .addEventListener("click", reiniciarMedicion);

document.addEventListener("keydown", (e) => {
  if (!landmarker) return;
  if (e.key === "e") alternarMenu();
  if (e.key === "r") reiniciarMedicion();
  if (menuAbierto && /^[1-9]$/.test(e.key)) {
    const claves = Object.keys(EJERCICIOS);
    const elegida = Number(e.key) - 1;
    if (elegida < claves.length) {
      cambiarEjercicio(claves[elegida]);
      alternarMenu(false);
    }
  }
});

cambiarEjercicio(EJERCICIO_INICIAL);
