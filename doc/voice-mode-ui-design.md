# Voice Mode UI Design Specification

## Research Summary

### 1. ChatGPT Advanced Voice Mode (2024-2025)

**Visual Design:**
- Single animated blue sphere (orb) centered on screen — replaces the old black dots
- Intentionally minimal: the orb IS the interface, filling all empty space
- No clutter, no controls visible during active conversation (just mute + end)
- Captions render under the orb as text overlay when toggled
- Desktop/web: stays minimal during conversation; full transcript appears only after voice mode ends

**State Behaviors:**
- **Idle/Start**: Orb activates with a calm blue glow, signaling voice mode is live
- **Listening**: Orb subtly pulses and shifts — audio-reactive deformation that tracks microphone input
- **Thinking**: Orb shows internal activity — subtle ripples or internal color shifts
- **Speaking**: Orb expands/brightens, pulses with output audio amplitude
- **Color**: Cool blue (#4A90D9) as primary, with slight warmth when active

**Emotional Feel:** Calm, trustworthy, non-intrusive. The orb breathes — it feels alive but never aggressive.

### 2. Gemini Live Voice Mode

**Visual Design:**
- Concentric gradient orbs using Google's signature 4-color palette (red, yellow, green, blue)
- Circles as foundational shape — "circles convey simplicity, harmony, and comfort"
- Gradients with sharp leading edges that diffuse at the tail — directional energy
- Compact overlay: circular widget with vibrant waveform on dark background

**State Behaviors:**
- **Idle**: Slow-drifting gradient orb, low energy
- **Listening**: Gradient contracts inward as input volume rises, traveling waves reshape the inner edge
- **Thinking**: Internal activity increases — gradient swirls and shifts color
- **Speaking**: Orb grows with output volume, moves more quickly, inner radial field oscillates
- **Waveform**: Blue waveform on dark background, more vibrant when active

**Emotional Feel:** Warm, optimistic, playful yet sophisticated. "Something ethereal — that in-between fuzzy space." Softness through pulsing gradient shapes.

**Key Insight from Google Design Team:**
> "Movement in Gemini is not merely decorative; it's an essential guiding element. Inner activity within the motion conveys thinking, analysis, and intelligence, making Gemini's processing feel more transparent."

### 3. Apple Siri Voice Mode (iOS 18.1+)

**Visual Design:**
- Edge-to-edge glowing light that wraps around the entire display border
- No more floating orb — the ENTIRE screen becomes the assistant
- Color: Multi-colored waves (purple, blue, pink, teal) that shift based on state
- In iOS 27: Swirling orb expands from the Dynamic Island (pill-shaped)

**State Behaviors:**
- **Activation**: Glow emanates from the side button position, spreads outward — spatial awareness
- **Listening**: Edge glow pulses and ripples in response to user's voice, like a visualizer
- **Speaking**: Glow intensifies, color shifts, waves become more pronounced
- **Thinking**: Subtle internal swirl within the edge glow
- **Response**: Glow moves and breathes with the assistant's speech rhythm

**Emotional Feel:** Magical, premium, immersive. "One of the most beautiful pieces of software design." The glow wraps you — it feels personal and responsive.

**Key Design Principle:** The animation begins from where you triggered it (button position). Spatial origin matters.

### 4. Open Source Implementations

**JARVIS-style HUD (Sara-the-ai-assistant):**
- 4-layer rotating arc segments with tick marks and glowing end caps
- Radar scanning line sweeping 360° continuously
- Center crosshair with pulsing glow effects
- Audio-reactive arcs respond to microphone input levels
- State-driven color: Cyan (standby) → Bright cyan (listening) → Purple (processing) → Green (speaking)

**Jarvis PyQt5 (amanimran786):**
- Multi-layer glow rings around central sphere
- Particle swarm inside the sphere with twinkle effects
- Latitude wave lines that animate when speaking
- Rotating dashed outer ring + counter-rotating mid ring
- Waveform bars around equator that react to audio
- Core glow that changes intensity per state

**Voice Orb Visualizer (OrbitingBucket):**
- Organic blob deformation using internal force systems
- 24-32 vertex points on the orb perimeter
- Audio-reactive offset from voice amplitude
- Smooth state transitions with lerp-based color changes

**react-ai-voice-visualizer:**
- 12 visualization components: fluid orbs, particle swarms, waveforms, neural networks
- State-aware animations: idle, listening, thinking, speaking
- Simplex noise for organic deformation
- Delta-time smoothing for frame-rate independent animation

---

## What Makes Voice Mode Feel "Alive"

### Filling Empty Space Without Text
1. **The orb IS the content** — no empty space to fill when the orb breathes, deforms, and reacts
2. **Layered depth**: Background gradient → glow aura → main orb → internal activity → particles → outer rings
3. **Subtle ambient motion** even in idle: slow breathing, gentle drift, micro-particles

### Showing States Visually
| State | Visual Treatment | Color | Motion |
|-------|-----------------|-------|--------|
| Idle | Calm, breathing orb | Muted slate/blue | Slow pulse, 0.3-0.5 Hz |
| Listening | Audio-reactive, expanding | Blue/cyan, bright | Microphone-driven, 1-3 Hz |
| Thinking | Internal activity, swirling | Purple/violet | Rotating internal elements, 2-4 Hz |
| Speaking | Output-reactive, projecting | Green/teal, vivid | Speaker-driven, 1.5-3 Hz |
| Error | Contraction, warning | Red/coral | Stutter, then settle |

### Emotional Feel by State
- **Idle**: "I'm here, ready when you are" — calm, warm, not demanding attention
- **Listening**: "I hear you, keep going" — responsive, encouraging, focused
- **Thinking**: "I'm working on it" — active but not anxious, purposeful
- **Speaking**: "Here's what I think" — confident, clear, rhythmic

---

## PyQt5 Implementation Design

### Architecture

```
VoiceModeOrb (QWidget)
├── Background gradient layer
├── Outer glow rings (animated)
├── Main orb body (radial gradient, deformed)
├── Internal particles (twinkle effect)
├── Latitude wave lines (audio-reactive)
├── Waveform bars (equatorial, audio-reactive)
├── Core glow (breathing)
├── Rotating accent ring
└── State transition manager (lerp-based)
```

### Color Palette (per state)

```python
# From existing sopno/ui/hud/visuals/theme.py STATE_ACCENT
# Extended with richer gradients

COLORS = {
    "idle": {
        "primary":    QColor(100, 130, 180),  # Muted steel blue
        "secondary":  QColor(60, 80, 120),    # Darker blue
        "glow":       QColor(80, 120, 170, 30),
        "particle":   QColor(140, 180, 220),
        "background": QColor(8, 12, 24),
    },
    "listening": {
        "primary":    QColor(94, 177, 245),   # Bright cyan-blue
        "secondary":  QColor(50, 130, 220),
        "glow":       QColor(94, 177, 245, 45),
        "particle":   QColor(160, 210, 255),
        "background": QColor(6, 10, 22),
    },
    "thinking": {
        "primary":    QColor(155, 140, 242),  # Purple-violet
        "secondary":  QColor(120, 100, 200),
        "glow":       QColor(155, 140, 242, 40),
        "particle":   QColor(190, 175, 255),
        "background": QColor(10, 8, 22),
    },
    "speaking": {
        "primary":    QColor(74, 222, 154),   # Teal-green
        "secondary":  QColor(40, 180, 120),
        "glow":       QColor(74, 222, 154, 40),
        "particle":   QColor(130, 240, 190),
        "background": QColor(6, 14, 16),
    },
    "error": {
        "primary":    QColor(240, 113, 120),  # Coral-red
        "secondary":  QColor(200, 80, 90),
        "glow":       QColor(240, 113, 120, 35),
        "particle":   QColor(255, 160, 165),
        "background": QColor(16, 8, 10),
    },
}
```

### Animation Parameters

```python
# Timing
TICK_MS = 33              # 30 fps timer interval
TRANSITION_SPEED = 0.06   # Lerp factor for state transitions (0.04-0.10)

# Orb geometry
ORB_RADIUS_RATIO = 0.35  # Orb radius as fraction of min(width, height)
PARTICLE_COUNT = 24       # Internal floating particles
WAVE_POINTS = 80          # Points along latitude wave lines
BARS_COUNT = 32           # Equatorial waveform bars
RING_SEGMENTS = 12        # Dashed segments on outer ring

# Breathing / idle motion
IDLE_BREATHE_FREQ = 1.4   # Hz
IDLE_BREATHE_AMP = 0.04   # Radius modulation amplitude (fraction)
IDLE_DRIFT_FREQ = 0.3     # Hz for slow color drift

# Listening reactivity
LISTEN_PULSE_FREQ = 5.0   # Hz for fast listening pulse
LISTEN_EXPAND_MAX = 0.12  # Max radius expansion from audio
LISTEN_RING_SPEED = 2.0   # Outer ring rotation speed (deg/frame)

# Thinking internal activity
THINK_SWIRL_SPEED = 2.2   # Hz for internal scan line
THINK_PARTICLE_SPEED = 1.8  # Particle orbit speed multiplier

# Speaking projection
SPEAK_PULSE_FREQ = 3.0    # Hz for speaking rhythm
SPEAK_BAR_REACT = 0.28    # Max bar height from audio
SPEAK_RING_SPEED = 3.5    # Ring rotation speed
```

### Layer-by-Layer Drawing (paintEvent)

#### Layer 1: Background Gradient
```python
def _draw_background(self, p, w, h, colors, breath):
    """Full-widget radial gradient background, subtly colored by state."""
    bg = colors["background"]
    glow = colors["glow"]
    grad = QRadialGradient(w/2, h/2, max(w, h) * 0.7)
    grad.setColorAt(0.0, QColor(bg.red()+8, bg.green()+8, bg.blue()+8, 255))
    grad.setColorAt(0.6, bg)
    grad.setColorAt(1.0, QColor(max(0, bg.red()-4), max(0, bg.green()-4), max(0, bg.blue()-4)))
    p.fillRect(0, 0, w, h, QBrush(grad))
```

#### Layer 2: Outer Glow Rings
```python
def _draw_glow_rings(self, p, cx, cy, r, colors, t, state, audio_level):
    """2-3 concentric semi-transparent rings that pulse with state."""
    glow = colors["glow"]
    for i in range(3):
        ring_r = r * (1.15 + 0.08 * i) + 4 * abs(math.sin(t * (2.0 + i*0.7)))
        alpha = int(glow.alpha() * (0.8 - i * 0.2) * (1.0 + 0.3 * audio_level))
        pen = QPen(QColor(glow.red(), glow.green(), glow.blue(), max(10, min(255, alpha))), 1.2 - i*0.3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), ring_r, ring_r)
```

#### Layer 3: Main Orb Body
```python
def _draw_orb(self, p, cx, cy, r, colors, t, state, audio_level):
    """Central sphere with radial gradient and subtle deformation."""
    primary = colors["primary"]
    secondary = colors["secondary"]

    # Apply audio-reactive radius modulation
    effective_r = r * (1.0 + audio_level * 0.15)

    # 3D shading gradient (offset light source)
    grad = QRadialGradient(cx - r*0.25, cy - r*0.25, r * 1.1)
    grad.setColorAt(0.0, QColor(primary.red()+40, primary.green()+40, primary.blue()+40, 255))
    grad.setColorAt(0.4, QColor(secondary.red(), secondary.green(), secondary.blue(), 255))
    grad.setColorAt(1.0, QColor(max(0, secondary.red()-30), max(0, secondary.green()-30), max(0, secondary.blue()-30), 255))

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))

    # Simple deformation: elliptical stretch based on state
    if state == "speaking":
        stretch_x = 1.0 + 0.05 * audio_level
        stretch_y = 1.0 - 0.03 * audio_level
    elif state == "listening":
        stretch_x = 1.0 - 0.02 * audio_level
        stretch_y = 1.0 + 0.04 * audio_level
    else:
        stretch_x = 1.0 + 0.01 * math.sin(t * 1.2)
        stretch_y = 1.0 - 0.01 * math.sin(t * 1.2)

    p.drawEllipse(QPointF(cx, cy),
                  effective_r * stretch_x,
                  effective_r * stretch_y)
```

#### Layer 4: Internal Particles
```python
def _draw_particles(self, p, cx, cy, r, colors, t, state, particles):
    """Floating luminous dots inside the orb — twinkle and drift."""
    particle_color = colors["particle"]
    boost = {"idle": 0.5, "listening": 0.8, "speaking": 1.0, "thinking": 0.7}.get(state, 0.5)

    for pt in particles:
        # Orbit position with slow drift
        angle = pt["angle"] + t * pt["speed"]
        dist = r * pt["dist"] * (0.6 + 0.4 * math.sin(t * pt["wobble_freq"] + pt["phase"]))

        px = cx + math.cos(angle) * dist
        py = cy + math.sin(angle) * dist * 0.85  # Slight vertical compression

        # Keep inside orb
        if (px - cx)**2 + (py - cy)**2 > (r * 0.75)**2:
            continue

        # Twinkle
        twinkle = 0.5 + 0.5 * math.sin(t * 2.3 + pt["phase"] * 5)
        alpha = int((40 + 180 * pt["brightness"] * twinkle) * boost)
        size = pt["size"] * (0.8 + 0.4 * twinkle)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(particle_color.red(), particle_color.green(),
                          particle_color.blue(), max(15, min(220, alpha))))
        p.drawEllipse(QPointF(px, py), size, size)
```

#### Layer 5: Latitude Wave Lines
```python
def _draw_wave_lines(self, p, cx, cy, r, colors, t, state, audio_level):
    """Horizontal sine waves clipped to orb shape — amplitude reacts to audio."""
    primary = colors["primary"]
    n_lines = 5
    wave_amp = (0.04 + 0.18 * audio_level) * r if state == "speaking" else (0.01 + 0.03 * audio_level) * r

    # Clip to orb
    clip = QPainterPath()
    clip.addEllipse(QPointF(cx, cy), r, r)
    p.setClipPath(clip)

    for i in range(n_lines):
        frac = (i + 1) / (n_lines + 1)  # 0..1
        line_y = cy - r + frac * r * 2

        # Compute visible width at this y
        dy = line_y - cy
        half_w = math.sqrt(max(0, r*r - dy*dy))
        if half_w < 3:
            continue

        path = QPainterPath()
        for s in range(WAVE_POINTS + 1):
            fx = (s / WAVE_POINTS) * 2 * half_w - half_w
            angle_along = (s / WAVE_POINTS) * 2 * math.pi
            wy = line_y + wave_amp * math.sin(angle_along * 3 + t * 2.5 + i * 0.8) * (1 - abs(dy)/r)
            if s == 0:
                path.moveTo(cx + fx, wy)
            else:
                path.lineTo(cx + fx, wy)

        alpha = int(35 + 50 * (1 - abs(frac - 0.5) * 2) + 30 * audio_level)
        pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), alpha), 0.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    p.setClipping(False)
```

#### Layer 6: Equatorial Waveform Bars
```python
def _draw_bars(self, p, cx, cy, r, colors, t, state, bar_values):
    """Radial bars around the orb equator — height driven by frequency data."""
    primary = colors["primary"]
    bar_max = r * 0.25

    for i, val in enumerate(bar_values):
        angle = (i / BARS_COUNT) * 2 * math.pi - math.pi / 2
        bar_h = val * bar_max

        x0 = cx + r * math.cos(angle)
        y0 = cy + r * math.sin(angle)
        x1 = cx + (r + bar_h) * math.cos(angle)
        y1 = cy + (r + bar_h) * math.sin(angle)

        alpha = int(70 + 170 * val)
        color = QColor(primary.red(), primary.green(), primary.blue(), max(20, min(240, alpha)))
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
```

#### Layer 7: Core Glow
```python
def _draw_core(self, p, cx, cy, r, colors, t, state, breath):
    """Bright central glow — breathing heart of the orb."""
    primary = colors["primary"]
    core_r = r * (0.20 + 0.08 * breath)

    grad = QRadialGradient(cx, cy, core_r)
    grad.setColorAt(0.0, QColor(min(255, primary.red()+100),
                                min(255, primary.green()+100),
                                min(255, primary.blue()+100), 220))
    grad.setColorAt(0.4, QColor(primary.red(), primary.green(), primary.blue(), 140))
    grad.setColorAt(1.0, QColor(primary.red(), primary.green(), primary.blue(), 0))

    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(cx, cy), core_r, core_r)
```

#### Layer 8: Rotating Accent Ring
```python
def _draw_ring(self, p, cx, cy, r, colors, t, state):
    """Dashed ring that rotates — speed varies by state."""
    primary = colors["primary"]
    speeds = {"idle": 0.5, "listening": 2.0, "thinking": 1.5, "speaking": 3.5}
    speed = speeds.get(state, 0.5)
    angle = t * speed * 15  # degrees per frame

    p.save()
    p.translate(cx, cy)
    p.rotate(angle)

    dash_r = r + 4
    pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 80), 1.2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)

    for i in range(RING_SEGMENTS):
        seg_angle = i * (360 / RING_SEGMENTS)
        p.drawArc(QRectF(-dash_r, -dash_r, dash_r*2, dash_r*2),
                  int(seg_angle * 16), int(20 * 16))

    p.restore()
```

### State Transition System

```python
class StateTransition:
    """Smooth lerp-based transitions between visual states."""

    def __init__(self):
        self._current = "idle"
        self._target = "idle"
        self._progress = 1.0  # 0..1, 1 = fully transitioned

        # Per-property lerped values
        self._radius_mod = 0.0
        self._glow_alpha = 0.3
        self._ring_speed = 0.5
        self._particle_boost = 0.5

    def set_state(self, new_state: str):
        if new_state != self._target:
            self._target = new_state
            self._progress = 0.0

    def update(self, dt: float):
        """Advance transition by dt seconds."""
        if self._progress < 1.0:
            self._progress = min(1.0, self._progress + dt * TRANSITION_SPEED * 60)
            # Ease-out cubic
            t = 1 - (1 - self._progress) ** 3

            # Lerp each visual property
            target_vals = STATE_CONFIG[self._target]
            current_vals = STATE_CONFIG[self._current]

            self._radius_mod = lerp(current_vals["radius_mod"], target_vals["radius_mod"], t)
            self._glow_alpha = lerp(current_vals["glow_alpha"], target_vals["glow_alpha"], t)
            self._ring_speed = lerp(current_vals["ring_speed"], target_vals["ring_speed"], t)
            self._particle_boost = lerp(current_vals["particle_boost"], target_vals["particle_boost"], t)

        if self._progress >= 1.0 and self._current != self._target:
            self._current = self._target

def lerp(a, b, t):
    return a + (b - a) * t
```

### Audio Level Integration

```python
class AudioLevelSource:
    """Provides smoothed audio level for visualization."""

    def __init__(self):
        self._raw = 0.0
        self._smoothed = 0.0
        self._peak = 0.0
        self._peak_decay = 0.95
        self._smoothing = 0.15  # Lerp factor per frame

    def update(self, rms_energy: float):
        """Call with raw RMS from microphone callback."""
        # Normalize: typical RMS 0-3000, map to 0-1
        self._raw = min(1.0, rms_energy / 3000.0)

    def tick(self):
        """Call once per frame to smooth the level."""
        self._smoothed += (self._raw - self._smoothed) * self._smoothing
        self._peak = max(self._raw, self._peak * self._peak_decay)

    @property
    def level(self) -> float:
        return self._smoothed

    @property
    def peak(self) -> float:
        return self._peak
```

### Particle System Setup

```python
import random

def create_particles(count=24):
    """Initialize particle positions for the orb interior."""
    particles = []
    for _ in range(count):
        particles.append({
            "angle": random.uniform(0, 2 * math.pi),
            "dist": random.uniform(0.2, 0.7),     # Distance from center (fraction of r)
            "size": random.uniform(1.0, 3.0),      # Pixel radius
            "speed": random.uniform(0.1, 0.4),     # Orbital speed (rad/s)
            "brightness": random.uniform(0.3, 1.0), # Base brightness
            "phase": random.uniform(0, 2 * math.pi),# Phase offset for twinkle
            "wobble_freq": random.uniform(0.8, 2.5),# Wobble frequency
        })
    return particles
```

### Integration with Existing Robot Face

The `AliveRobotFace` widget already handles:
- Blinking, gaze direction, mouth animation
- State-driven accent colors via `STATE_ACCENT`
- Aura glow around the head

The `VoiceModeOrb` should be a separate widget that:
1. Contains the `AliveRobotFace` at its center (scaled to fit)
2. Draws all the surrounding visual layers around it
3. Shares the same state system — when `VoiceModeOrb.set_state("listening")` is called, both the orb layers and the robot face update together

```python
class VoiceModeOrb(QWidget):
    """Complete voice mode visualization with robot face center."""

    def __init__(self, parent=None, size=400):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._state_mgr = StateTransition()
        self._audio = AudioLevelSource()
        self._particles = create_particles(PARTICLE_COUNT)
        self._bars = [0.0] * BARS_COUNT
        self._t = 0.0
        self._breath = 0.0

        # Central robot face (scaled to fit inside the orb)
        face_size = int(size * 0.45)
        self._face = AliveRobotFace(self, size=face_size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def set_state(self, state: str):
        self._state_mgr.set_state(state)
        self._face.set_state(state)

    def set_audio_level(self, rms: float):
        self._audio.update(rms)

    def _tick(self):
        dt = TICK_MS / 1000.0
        self._t += dt
        self._breath = 0.5 + 0.5 * math.sin(self._t * IDLE_BREATHE_FREQ)
        self._audio.tick()
        self._state_mgr.update(dt)

        # Update bar values (in real implementation, driven by FFT data)
        for i in range(BARS_COUNT):
            target = self._audio.level * (0.5 + 0.5 * math.sin(self._t * 3 + i * 0.3))
            self._bars[i] += (target - self._bars[i]) * 0.2

        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        r = min(w, h) * ORB_RADIUS_RATIO
        state = self._state_mgr._current
        colors = COLORS[state]
        audio = self._audio.level

        self._draw_background(p, w, h, colors, self._breath)
        self._draw_glow_rings(p, cx, cy, r, colors, self._t, state, audio)
        self._draw_orb(p, cx, cy, r, colors, self._t, state, audio)
        self._draw_particles(p, cx, cy, r, colors, self._t, state, self._particles)
        self._draw_wave_lines(p, cx, cy, r, colors, self._t, state, audio)
        self._draw_bars(p, cx, cy, r, colors, self._t, state, self._bars)
        self._draw_core(p, cx, cy, r, colors, self._t, state, self._breath)
        self._draw_ring(p, cx, cy, r, colors, self._t, state)

        p.end()
```

---

## Easing Curves Reference

| Transition | Curve | Duration | Notes |
|------------|-------|----------|-------|
| Idle → Listening | Ease-out cubic | 400ms | Quick response, feels immediate |
| Listening → Thinking | Ease-in-out quad | 300ms | Smooth shift, not jarring |
| Thinking → Speaking | Ease-out back | 350ms | Slight overshoot, feels alive |
| Speaking → Listening | Ease-out cubic | 300ms | Quick return |
| Any → Error | Ease-in expo | 200ms | Sharp contraction |
| Error → Any | Ease-out quad | 600ms | Gradual recovery |
| State color lerp | Ease-out cubic | 500ms | Colors blend smoothly |

---

## Performance Budget

- **Target**: 30fps (33ms timer) on mid-range hardware
- **QPainter layers**: 8 draw calls per frame (well within budget)
- **Particles**: 24 circles (trivial)
- **Wave lines**: 5 paths × 80 points each (400 points total, fast)
- **Bars**: 32 lines (trivial)
- **Ring**: 12 arcs (trivial)
- **Gradient fills**: 3-4 per frame (QRadialGradient is GPU-accelerated on most systems)
- **Total**: Should comfortably run at 30fps, with headroom for 60fps if desired

---

## Key Design Principles

1. **The orb IS the content** — never feels empty because it breathes, deforms, and reacts
2. **Layer depth creates richness** — 8 layers from background to foreground
3. **Audio reactivity makes it conversational** — the orb responds to real voice data
4. **Color tells the story** — state changes are instantly readable through hue shifts
5. **Motion is purposeful** — idle is calm, listening is responsive, speaking is confident
6. **The robot face is the soul** — surrounded by the orb's body, giving personality
7. **Transitions are smooth** — lerp-based with cubic easing, never abrupt
8. **Performance first** — all QPainter, no OpenGL dependency, 30fps target
