export const LADO = "auto";

export const DURACION_MIN_REP = 0.5;
export const MARGEN_UMBRAL = 0.15;
export const RUIDO_MAXIMO = 0.15;
export const VENTANA_CALIBRACION = 300;

export const UMBRAL_VISIBILIDAD = 0.5;
export const TOLERANCIA_LONGITUD = 0.4;
export const FILTRO_CORTE = 1.0;
export const FILTRO_BETA = 10.0;

export const PUNTOS = {
  derecho: {
    hombro: [12],
    codo: [14],
    muneca: [16, 18, 20, 22],
    cadera: [24],
    rodilla: [26],
    tobillo: [28, 30, 32],
  },
  izquierdo: {
    hombro: [11],
    codo: [13],
    muneca: [15, 17, 19, 21],
    cadera: [23],
    rodilla: [25],
    tobillo: [27, 29, 31],
  },
};

export const EJERCICIOS = {
  curl: {
    nombre: "Curl de biceps",
    vista: "de perfil",
    puntos: ["hombro", "codo", "muneca"],
    contarEn: "up",
    amplitudMin: 50,
  },
  sentadilla: {
    nombre: "Sentadilla",
    vista: "de perfil, cuerpo entero",
    puntos: ["cadera", "rodilla", "tobillo"],
    contarEn: "up",
    amplitudMin: 45,
  },
  press: {
    nombre: "Press de hombros",
    vista: "de frente",
    puntos: ["hombro", "codo", "muneca"],
    contarEn: "ciclo",
    amplitudMin: 45,
  },
  elevacion: {
    nombre: "Elevacion lateral",
    vista: "de frente",
    puntos: ["cadera", "hombro", "codo"],
    contarEn: "ciclo",
    amplitudMin: 35,
  },
};

export const NOMBRES = {
  hombro: "el hombro",
  codo: "el codo",
  muneca: "la mano",
  cadera: "la cadera",
  rodilla: "la rodilla",
  tobillo: "el pie",
};

export const CONEXIONES = [
  [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
  [11, 23], [12, 24], [23, 24],
  [23, 25], [25, 27], [27, 29], [27, 31],
  [24, 26], [26, 28], [28, 30], [28, 32],
  [15, 17], [15, 19], [15, 21],
  [16, 18], [16, 20], [16, 22],
];

export class FiltroUnEuro {
  constructor(corte, beta, corteDerivada = 1.0) {
    this.corte = corte;
    this.beta = beta;
    this.corteDerivada = corteDerivada;
    this.x = null;
    this.dx = null;
    this.t = null;
  }

  static alfa(corte, dt) {
    const tau = 1 / (2 * Math.PI * corte);
    return 1 / (1 + tau / dt);
  }

  aplicar(valor, t) {
    if (this.x === null || t <= this.t) {
      this.x = valor.slice();
      this.dx = valor.map(() => 0);
      this.t = t;
      return this.x;
    }

    const dt = t - this.t;
    const alfaD = FiltroUnEuro.alfa(this.corteDerivada, dt);
    this.dx = valor.map(
      (v, i) => alfaD * ((v - this.x[i]) / dt) + (1 - alfaD) * this.dx[i],
    );

    const velocidad = Math.hypot(...this.dx);
    const alfa = FiltroUnEuro.alfa(this.corte + this.beta * velocidad, dt);
    this.x = valor.map((v, i) => alfa * v + (1 - alfa) * this.x[i]);
    this.t = t;
    return this.x;
  }
}

export class Suavizador {
  constructor(corte, beta) {
    this.corte = corte;
    this.beta = beta;
    this.filtros = new Map();
  }

  aplicar(clave, valor, t) {
    if (!this.filtros.has(clave)) {
      this.filtros.set(clave, new FiltroUnEuro(this.corte, this.beta));
    }
    return this.filtros.get(clave).aplicar(valor, t);
  }

  reiniciar() {
    this.filtros.clear();
  }
}

export function calcularAngulo(a, b, c) {
  const ba = a.map((v, i) => v - b[i]);
  const bc = c.map((v, i) => v - b[i]);

  const norma = Math.hypot(...ba) * Math.hypot(...bc);
  if (norma === 0) return null;

  const punto = ba.reduce((acc, v, i) => acc + v * bc[i], 0);
  const coseno = Math.min(1, Math.max(-1, punto / norma));
  return (Math.acos(coseno) * 180) / Math.PI;
}

export function confianza(lm) {
  return lm?.visibility ?? 1;
}

export function confianzaGrupo(landmarks, indices) {
  return Math.max(...indices.map((i) => confianza(landmarks[i])));
}

export function puntoGrupo(mundo, landmarks, indices) {
  let peso = 0;
  const suma = [0, 0, 0];
  for (const i of indices) {
    const c = confianza(landmarks[i]);
    if (c > 0.05) {
      suma[0] += mundo[i].x * c;
      suma[1] += mundo[i].y * c;
      suma[2] += mundo[i].z * c;
      peso += c;
    }
  }
  return peso === 0 ? null : suma.map((v) => v / peso);
}

export function mediana(valores) {
  const orden = [...valores].sort((a, b) => a - b);
  const medio = Math.floor(orden.length / 2);
  return orden.length % 2 ? orden[medio] : (orden[medio - 1] + orden[medio]) / 2;
}

export function percentil(valores, p) {
  const orden = [...valores].sort((a, b) => a - b);
  const pos = (orden.length - 1) * (p / 100);
  const bajo = Math.floor(pos);
  const alto = Math.ceil(pos);
  return bajo === alto
    ? orden[bajo]
    : orden[bajo] + (orden[alto] - orden[bajo]) * (pos - bajo);
}

function distancia(a, b) {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export function longitudesPlausibles(a, b, c, historial) {
  const primero = distancia(a, b);
  const segundo = distancia(b, c);

  if (primero <= 0 || segundo <= 0) return [false, null];
  if (historial.length < 10) return [true, [primero, segundo]];

  const refA = mediana(historial.map((h) => h[0]));
  const refB = mediana(historial.map((h) => h[1]));
  const valido =
    Math.abs(primero - refA) / refA <= TOLERANCIA_LONGITUD &&
    Math.abs(segundo - refB) / refB <= TOLERANCIA_LONGITUD;
  return [valido, [primero, segundo]];
}

export function elegirLado(landmarks, ladoActual, ejercicio) {
  if (LADO !== "auto") return LADO;

  const extremos = [ejercicio.puntos[0], ejercicio.puntos[2]];
  const puntajes = {};
  for (const [nombre, grupos] of Object.entries(PUNTOS)) {
    puntajes[nombre] = Math.min(
      ...extremos.map((p) => confianzaGrupo(landmarks, grupos[p])),
    );
  }

  const mejor = puntajes.derecho >= puntajes.izquierdo ? "derecho" : "izquierdo";
  if (ladoActual === null || puntajes[ladoActual] < UMBRAL_VISIBILIDAD) {
    if (ladoActual === null || puntajes[mejor] > puntajes[ladoActual] + 0.25) {
      return mejor;
    }
  }
  return ladoActual;
}

export class MaquinaRepeticiones {
  constructor(ejercicio) {
    this.ejercicio = ejercicio;
    this.contador = 0;
    this.estado = null;
    this.historial = [];
    this.ultima = 0;
  }

  get recorrido() {
    if (this.historial.length < 30) return null;

    const bajo = percentil(this.historial, 5);
    const alto = percentil(this.historial, 95);
    const recorrido = alto - bajo;

    if (recorrido < this.ejercicio.amplitudMin) return null;

    const saltos = [];
    for (let i = 1; i < this.historial.length; i++) {
      saltos.push(Math.abs(this.historial[i] - this.historial[i - 1]));
    }
    if (mediana(saltos) > RUIDO_MAXIMO * recorrido) return null;

    return [bajo, alto];
  }

  get umbrales() {
    const recorrido = this.recorrido;
    if (recorrido === null) return null;

    const [bajo, alto] = recorrido;
    const margen = MARGEN_UMBRAL * (alto - bajo);
    return [bajo + margen, alto - margen];
  }

  actualizar(angulo, ahora) {
    this.historial.push(angulo);
    if (this.historial.length > VENTANA_CALIBRACION) this.historial.shift();

    const umbrales = this.umbrales;
    if (umbrales === null) return;

    const [flexionado, extendido] = umbrales;
    let nuevo = this.estado;
    if (angulo < flexionado) nuevo = "up";
    else if (angulo > extendido) nuevo = "down";

    const objetivo =
      this.ejercicio.contarEn === "up" ? ["down", "up"] : ["up", "down"];
    if (
      this.estado === objetivo[0] &&
      nuevo === objetivo[1] &&
      ahora - this.ultima > DURACION_MIN_REP
    ) {
      this.contador += 1;
      this.ultima = ahora;
    }

    this.estado = nuevo;
  }

  reiniciar() {
    this.contador = 0;
    this.estado = null;
    this.historial = [];
  }
}

export function redactarAviso(vis, ejercicio, angulo, calibrada) {
  if (!vis) return "No detecto a nadie en la imagen";

  const extremos = [ejercicio.puntos[0], ejercicio.puntos[2]];
  const flojos = extremos.filter((p) => vis[p] < UMBRAL_VISIBILIDAD);
  if (flojos.length) {
    return "No veo bien " + flojos.map((p) => NOMBRES[p]).join(" ni ");
  }
  if (angulo === null) {
    return "No puedo ubicar " + NOMBRES[ejercicio.puntos[1]] + " con seguridad";
  }
  if (!calibrada) return "Calibrando: realizar una repetición completa y lenta";
  return null;
}
