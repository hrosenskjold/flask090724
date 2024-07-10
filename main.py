import os
import json
import requests
import zipfile
import shapefile  # pyshp library
from shapely.geometry import shape, mapping
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

app = Flask(__name__, template_folder='templates')
app.config['UPLOAD_FOLDER'] = '/tmp'
app.config['ALLOWED_EXTENSIONS'] = {'geojson', 'zip'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def convert_geojson_to_arcgis(geojson):
    arcgis_features = []
    for feature in geojson['features']:
        geometry_type = feature['geometry']['type']
        if geometry_type == "Polygon":
            geometry = {
                "rings": feature['geometry']['coordinates'],
                "spatialReference": {"wkid": 4326}
            }
        elif geometry_type == "MultiPolygon":
            rings = []
            for polygon in feature['geometry']['coordinates']:
                rings.extend(polygon)
            geometry = {
                "rings": rings,
                "spatialReference": {"wkid": 4326}
            }
        else:
            raise ValueError(f"Unsupported geometry type: {geometry_type}")
        
        arcgis_feature = {
            "geometry": geometry,
            "attributes": feature['properties']
        }
        arcgis_features.append(arcgis_feature)
    return arcgis_features

def convert_shapefile_to_geojson(shapefile_path):
    with shapefile.Reader(shapefile_path) as shp:
        fields = [field[0] for field in shp.fields if field[0] != 'DeletionFlag']
        features = []
        for sr in shp.shapeRecords():
            attributes = dict(zip(fields, sr.record))
            geom = sr.shape.__geo_interface__
            features.append({"type": "Feature", "geometry": geom, "properties": attributes})
        return {"type": "FeatureCollection", "features": features}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'})
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if filename.endswith('.geojson'):
            with open(filepath, 'r') as f:
                geojson_data = json.load(f)
        elif filename.endswith('.zip'):
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(app.config['UPLOAD_FOLDER'])
                for fname in zip_ref.namelist():
                    if fname.endswith('.shp'):
                        shapefile_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
                        geojson_data = convert_shapefile_to_geojson(shapefile_path)
                        break
                else:
                    return jsonify({'error': 'No shapefile found in ZIP'})
        else:
            return jsonify({'error': 'File type not supported'})

        features = convert_geojson_to_arcgis(geojson_data)
        
        url = "https://services6.arcgis.com/QHir1urgnGYroCLG/ArcGIS/rest/services/PG_versioneret_110624/FeatureServer/0/addFeatures"
        
        data = {
            "features": json.dumps(features),
            "f": "json"
        }
        
        response = requests.post(url, data=data)
        
        return jsonify(response.json())
    
    return jsonify({'error': 'File not allowed'})

if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))
