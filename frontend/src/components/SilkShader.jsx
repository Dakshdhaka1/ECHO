import { useEffect, useRef } from 'react'
import { useTheme } from '../context/ThemeContext'

// "Silk ribbons" background from the ECHO Stitch project (screen "Shader"): emerald-to-teal light ribbons over
// charcoal. Ported to a React leaf component: renders at reduced resolution, pauses off-screen and in hidden tabs,
// draws a single still frame under prefers-reduced-motion, and has a light variant (dark ribbons on paper).
const VERTEX = `attribute vec2 a_position;
void main() { gl_Position = vec4(a_position, 0.0, 1.0); }`

const FRAGMENT = `precision highp float;
uniform float u_time;
uniform vec2 u_resolution;
uniform vec2 u_mouse;
uniform float u_light;

float hash(vec2 p) { p = fract(p * vec2(234.34, 435.345)); p += dot(p, p + 34.23); return fract(p.x * p.y); }
float noise(vec2 p) {
  vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

void main() {
  vec2 uv = gl_FragCoord.xy / u_resolution.xy;
  vec2 p = (gl_FragCoord.xy * 2.0 - u_resolution.xy) / min(u_resolution.x, u_resolution.y);
  float t = u_time * 0.35;
  vec2 m = (u_mouse / u_resolution - 0.5) * 0.3;
  p += m * smoothstep(1.2, 0.0, length(p));

  vec3 acc = vec3(0.0);
  for (float i = 1.0; i <= 6.0; i += 1.0) {
    float speed = t * (0.4 + i * 0.1);
    float y = sin(p.x * (1.8 + i * 0.3) + speed + i * 0.45) * 0.25 + sin(p.x * 3.4 - speed * 0.7) * 0.12
            + noise(vec2(p.x * 2.0, t * 0.2)) * 0.15;
    float glow = 0.015 / (abs(p.y - y + 0.15) + 0.02);
    vec3 waveColor = mix(vec3(0.06, 0.45, 0.35), vec3(0.12, 0.78, 0.68), sin(p.x * 1.5 + speed) * 0.5 + 0.5);
    acc += waveColor * glow * (0.8 / i);
  }
  float vig = smoothstep(1.6, 0.3, length(uv - 0.5));
  vec3 dark = (vec3(0.035, 0.039, 0.051) + acc) * vig;
  vec3 paper = vec3(0.973, 0.973, 0.965);
  float ink = clamp(dot(acc, vec3(0.2, 0.6, 0.2)) * 0.55, 0.0, 0.6) * vig;
  vec3 light = mix(paper, vec3(0.08, 0.40, 0.27), ink);
  gl_FragColor = vec4(mix(dark, light, u_light), 1.0);
}`

export default function SilkShader({ className = '', scale = 0.6 }) {
  const canvas = useRef(null)
  const { dark } = useTheme()
  const lightRef = useRef(dark ? 0 : 1)
  lightRef.current = dark ? 0 : 1

  useEffect(() => {
    const el = canvas.current
    const gl = el?.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (!gl) return undefined
    const compile = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s }
    const prog = gl.createProgram()
    gl.attachShader(prog, compile(gl.VERTEX_SHADER, VERTEX))
    gl.attachShader(prog, compile(gl.FRAGMENT_SHADER, FRAGMENT))
    gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return undefined
    gl.useProgram(prog)
    gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer())
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW)
    const pos = gl.getAttribLocation(prog, 'a_position')
    gl.enableVertexAttribArray(pos)
    gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0)
    const u = (n) => gl.getUniformLocation(prog, n)
    const [uTime, uRes, uMouse, uLight] = ['u_time', 'u_resolution', 'u_mouse', 'u_light'].map(u)

    const mouse = { x: 0.5, y: 0.5 }
    const target = { x: 0.5, y: 0.5 }
    const size = () => {
      const w = Math.max(1, Math.round(el.clientWidth * scale))
      const h = Math.max(1, Math.round(el.clientHeight * scale))
      if (el.width !== w || el.height !== h) { el.width = w; el.height = h }
    }
    const draw = (ms) => {
      size()
      mouse.x += (target.x - mouse.x) * 0.05
      mouse.y += (target.y - mouse.y) * 0.05
      gl.viewport(0, 0, el.width, el.height)
      gl.uniform1f(uTime, ms * 0.001)
      gl.uniform2f(uRes, el.width, el.height)
      gl.uniform2f(uMouse, mouse.x * el.width, mouse.y * el.height)
      gl.uniform1f(uLight, lightRef.current)
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4)
    }

    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    let frame = 0
    let visible = true
    const loop = (ms) => { draw(ms); frame = requestAnimationFrame(loop) }
    const start = () => { if (!frame && visible && !document.hidden && !still) frame = requestAnimationFrame(loop) }
    const stop = () => { cancelAnimationFrame(frame); frame = 0 }

    const onMove = (e) => {
      const r = el.getBoundingClientRect()
      if (r.width && r.height) { target.x = (e.clientX - r.left) / r.width; target.y = 1 - (e.clientY - r.top) / r.height }
    }
    const onVisibility = () => (document.hidden ? stop() : start())
    const io = typeof IntersectionObserver !== 'undefined'
      ? new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; visible ? start() : stop() })
      : null
    io?.observe(el)
    window.addEventListener('pointermove', onMove, { passive: true })
    document.addEventListener('visibilitychange', onVisibility)
    if (still) draw(12000)
    else start()
    return () => {
      stop()
      io?.disconnect()
      window.removeEventListener('pointermove', onMove)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [scale])

  return <canvas ref={canvas} className={`block h-full w-full ${className}`} aria-hidden />
}
