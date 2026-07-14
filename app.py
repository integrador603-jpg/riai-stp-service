import os, math, tempfile, traceback
from collections import defaultdict
from flask import Flask, request, jsonify
from flask_cors import CORS

print("Flask importing...", flush=True)
app = Flask(__name__)
CORS(app)
print("Flask ready.", flush=True)

MAX_FILE_MB = 50

@app.route('/', methods=['GET'])
def index():
    return jsonify({'status': 'ok', 'service': 'RIAI STP Analyzer'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'RIAI STP Analyzer'})

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No se recibió ningún archivo.'}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({'status': 'error', 'message': 'Nombre de archivo vacío.'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ('.stp', '.step'):
        return jsonify({'status': 'error', 'message': 'Solo se aceptan archivos .stp o .step'}), 400

    f.seek(0, 2)
    size_mb = f.tell() / (1024 * 1024)
    f.seek(0)
    if size_mb > MAX_FILE_MB:
        return jsonify({'status': 'error', 'message': f'Archivo demasiado grande ({size_mb:.1f} MB). Máx {MAX_FILE_MB} MB.'}), 400

    suffix = '.stp' if ext == '.stp' else '.step'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        result = analyze_step(tmp_path)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Error al procesar el archivo: {str(e)}',
            'detail': traceback.format_exc(),
        }), 500
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


def analyze_step(filepath):
    print(f"Loading cadquery...", flush=True)
    import cadquery as cq
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    print(f"Importing STEP: {filepath}", flush=True)

    shape = cq.importers.importStep(filepath)
    faces = shape.faces().vals()
    bb    = shape.val().BoundingBox()
    vol   = shape.val().Volume()

    L = round(bb.xmax - bb.xmin, 2)
    W = round(bb.ymax - bb.ymin, 2)
    H = round(bb.zmax - bb.zmin, 2)

    types = {}
    cylinders = []

    for f in faces:
        gt = f.geomType()
        types[gt] = types.get(gt, 0) + 1
        if gt == 'CYLINDER':
            adaptor = BRepAdaptor_Surface(f.wrapped)
            r  = adaptor.Cylinder().Radius()
            ax = adaptor.Cylinder().Axis()
            lc = ax.Location()
            box = Bnd_Box()
            BRepBndLib.Add_s(f.wrapped, box)
            xmn,ymn,zmn,xmx,ymx,zmx = box.Get()
            cylinders.append({
                'r':  round(r, 2),
                'cx': round(lc.X(), 1),
                'cy': round(lc.Y(), 1),
                'cz': round(lc.Z(), 1),
                'h':  round(max(xmx-xmn, ymx-ymn, zmx-zmn), 1),
            })

    n_faces = len(faces)
    n_bsp   = types.get('BSPLINE', 0)
    is_simple = n_faces < 30 and n_bsp == 0

    by_r = defaultdict(list)
    for c in cylinders:
        by_r[round(c['r'], 0)].append(c)

    structural = []
    for rk, grp in sorted(by_r.items(), reverse=True):
        h_max  = max(c['h'] for c in grp)
        n_axes = len(set((c['cx'], c['cy'], c['cz']) for c in grp))
        vol_cyl = math.pi * (rk ** 2) * h_max
        if vol_cyl > vol * 0.001:
            structural.append({
                'diameter_mm': round(rk * 2, 1),
                'height_mm':   round(h_max, 1),
                'instances':   n_axes,
            })

    vol_bb = L * W * H
    eff    = round(vol / vol_bb * 100, 1) if vol_bb > 0 else 0

    orientations = [
        {'label': 'L×W×H', 'x': round(L/10,2), 'y': round(W/10,2), 'z': round(H/10,2)},
        {'label': 'W×L×H', 'x': round(W/10,2), 'y': round(L/10,2), 'z': round(H/10,2)},
        {'label': 'H×W×L', 'x': round(H/10,2), 'y': round(W/10,2), 'z': round(L/10,2)},
        {'label': 'L×H×W', 'x': round(L/10,2), 'y': round(H/10,2), 'z': round(W/10,2)},
        {'label': 'W×H×L', 'x': round(W/10,2), 'y': round(H/10,2), 'z': round(L/10,2)},
        {'label': 'H×L×W', 'x': round(H/10,2), 'y': round(L/10,2), 'z': round(W/10,2)},
    ]

    print(f"Done: {L}x{W}x{H}mm", flush=True)
    return {
        'status': 'ok',
        'filename': os.path.basename(filepath),
        'bbox': {
            'L_mm': L, 'W_mm': W, 'H_mm': H,
            'L_cm': round(L/10, 2), 'W_cm': round(W/10, 2), 'H_cm': round(H/10, 2),
            'L_in': round(L/25.4, 3), 'W_in': round(W/25.4, 3), 'H_in': round(H/25.4, 3),
        },
        'volume': {
            'real_mm3':  round(vol, 0),
            'real_cm3':  round(vol / 1000, 1),
            'bbox_cm3':  round(vol_bb / 1000, 1),
            'efficiency_pct': eff,
        },
        'faces': {
            'total':    n_faces,
            'plane':    types.get('PLANE', 0),
            'cylinder': types.get('CYLINDER', 0),
            'cone':     types.get('CONE', 0),
            'bspline':  n_bsp,
            'other':    types.get('TORUS', 0) + types.get('SPHERE', 0) + types.get('EXTRUSION', 0),
        },
        'complexity': 'simple' if is_simple else 'complex',
        'structural_cylinders': structural[:8],
        'orientations': orientations,
        'note': (
            'Pieza simple — se detectaron cilindros estructurales.'
            if is_simple else
            f'Pieza compleja ({n_faces} caras). Se recomienda usar el bounding box global.'
        ),
    }


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    print(f"Starting on port {port}", flush=True)
    app.run(host='0.0.0.0', port=port, debug=False)
