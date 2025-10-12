from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
import os

# PDF im selben Ordner speichern wie das Skript
base_dir = os.path.dirname(os.path.abspath(__file__))
pdf_path = os.path.join(base_dir, "Upper_Body_Hygiene_Foundations_Final_Design.pdf")

# Create canvas
c = canvas.Canvas(pdf_path, pagesize=A4)
width, height = A4

# --- Background gradient (light blue top fade) ---
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import Color

def draw_gradient(c, x, y, w, h, start_color, end_color, steps=50):
    for i in range(steps):
        ratio = i / float(steps - 1)
        r = start_color.red + (end_color.red - start_color.red) * ratio
        g = start_color.green + (end_color.green - start_color.green) * ratio
        b = start_color.blue + (end_color.blue - start_color.blue) * ratio
        c.setFillColor(Color(r, g, b))
        c.rect(x, y + i * (h / steps), w, h / steps, stroke=0, fill=1)

# Light blue to white gradient header
draw_gradient(c, 0, height - 180, width, 180, colors.Color(0.85, 0.92, 1), colors.white)

# --- Title & Icon ---
c.setFont("Helvetica-Bold", 20)
c.setFillColor(colors.black)
c.drawString(60, height - 100, "Upper Body Hygiene Routine – Foundations")

# Small line-art style silhouette icon placeholder (simple outline)
c.setLineWidth(2)
c.setStrokeColor(colors.black)

"""
x = width - 200   # weiter nach links (von rechtsrand)
y = height - 500  # weiter nach unten

c.circle(x, y, 20, stroke=1, fill=0)
c.line(width - 120, height - 130, width - 120, height - 160)
c.line(width - 120, height - 160, width - 140, height - 180)
c.line(width - 120, height - 160, width - 100, height - 180)
"""
# --- Main Text ---
c.setFont("Helvetica", 11)
text = c.beginText(60, height - 220)
text.setLeading(15)
text.textLines('''
Goal of the Routine:

- High frequency - low intesity @home training
- Recover faster between training sessions
- Maintain posture & pump – reduce tension & pain
- Improve mobility, strength, and awareness in joints

Exercises(sorted by joints):

NECK
- Slow controlled nods, rotations, and twists
- Gentle band resisted neck motion – light resistance for postural control

SHOULDERS
- Shoulder CARs beside body + 1 min 90° iso hold
- Cuban rotations (45°/90°) – focus on cuff and delts
- Band pull-aparts – retraction tool for rear delts

ELBOWS & ARMS
- Elbows – flexion/extension with gentle rotation awareness
- Arms (front/lateral/rear delts) – controlled raises, focus on delts

WRISTS & FINGERS
- Wrist rotations, gentle circles, full flexion, extension, pronation, deviation, supination
- Banded wrist exercises – controlled flexion/extension with tension
- Light dumbbell work for wrists – controlled small-range motion

UPPER BODY / TORSO
- Upper body rotations – rib cage extensions, rotations, and slow torso twists
- Floor rocks – wrist + shoulder mobility under load


Notes:

- Smooth & controlled movements
- Breathe & stay relaxed
- Consistency > intensity

Observe your posture and symmetry before starting any upper body routine.
Use a mirror or camera for self-check and awareness.''')
c.drawText(text)

# --- Insert side images ---
try:
    c.drawImage("/mnt/data/ChatGPT Image 10. Okt. 2025, 13_57_56.png", width - 220, height - 450, width=150, preserveAspectRatio=True, mask='auto')
    c.drawImage("/mnt/data/ChatGPT Image 10. Okt. 2025, 14_53_06.png", width - 220, height - 700, width=150, preserveAspectRatio=True, mask='auto')
except:
    pass

c.showPage()
c.save()

pdf_path