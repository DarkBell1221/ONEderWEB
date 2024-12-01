from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit
from werkzeug.security import check_password_hash, generate_password_hash
import os
from flask_cors import CORS
from dotenv import load_dotenv

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Configuración de la aplicación Flask
app = Flask(
    __name__,
    template_folder=os.path.join(os.getcwd(), 'public_html'),
    static_folder=os.path.join(os.getcwd(), 'public_html', 'assets')
)

# Configuración de la base de datos
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:MbeVKVhkqVhdFAiVuouloQWGmMXfGiTk@mysql.railway.internal:3306/railway'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar SQLAlchemy
db = SQLAlchemy(app)

# Configuración de correo (Flask-Mail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # Tu correo
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # Contraseña
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')  # Remitente

# Inicializar extensiones
mail = Mail(app)
socketio = SocketIO(app)  # Inicializar SocketIO
CORS(app)  # Manejar solicitudes CORS si es necesario

# Clave secreta para manejar sesiones
app.secret_key = os.getenv("FLASK_SECRET_KEY", "mi_clave_secreta")

# Datos de usuario permitidos
ALLOWED_EMAIL = "bellwhite183@gmail.com"
ALLOWED_PASSWORD = generate_password_hash("HOLA1234")  # Usar hash para la contraseña

# Modelo de base de datos para videos
class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(255), unique=True, nullable=False)

@app.route('/')
def home():
    """Renderiza la página principal con videos de la base de datos y de YouTube."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        db_videos = Video.query.all()
        return render_template('index.html', db_videos=db_videos)

    except Exception as e:
        print(f"Error al renderizar la página: {e}")
        return jsonify({"success": False, "message": "Error al cargar la página"}), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Ruta para mostrar y procesar el formulario de inicio de sesión"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        # Verificar la contraseña con el hash
        if email == ALLOWED_EMAIL and check_password_hash(ALLOWED_PASSWORD, password):
            session['user_id'] = email

            try:
                msg = Message("Nuevo inicio de sesión",
                              recipients=[os.getenv('MAIL_USERNAME')])
                msg.body = f"Un usuario ha iniciado sesión con el correo: {email}"
                mail.send(msg)
            except Exception as e:
                print(f"Error al enviar correo: {e}")

            return redirect(url_for('home'))
        else:
            return jsonify({"success": False, "message": "Correo o contraseña incorrectos"}), 401

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Ruta para cerrar sesión"""
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/add-video', methods=['POST'])
def add_video():
    try:
        video_id = request.json.get('video_id')

        if not video_id or video_id.strip() == "":
            return jsonify({"success": False, "message": "El ID del video es requerido"}), 400

        existing_video = Video.query.filter_by(video_id=video_id).first()

        if existing_video:
            return jsonify({"success": False, "message": "Este video ya está en la base de datos"}), 400

        new_video = Video(video_id=video_id)
        db.session.add(new_video)
        db.session.commit()

        socketio.emit('nuevo_video', {'video_id': video_id})
        return jsonify({"success": True, "message": "Video agregado correctamente"}), 200

    except Exception as e:
        print(f"Error en /add-video: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500

@app.route('/delete-video', methods=['POST'])
def delete_video():
    """Eliminar un video de la base de datos y notificar en tiempo real"""
    try:
        video_id = request.json.get('video_id')

        if not video_id:
            return jsonify({"success": False, "message": "El ID del video es requerido"}), 400

        video_to_delete = Video.query.filter_by(video_id=video_id).first()

        if not video_to_delete:
            return jsonify({"success": False, "message": "El video no existe en la base de datos"}), 404

        db.session.delete(video_to_delete)
        db.session.commit()

        socketio.emit('eliminar_video', {'video_id': video_id})
        return jsonify({"success": True, "message": "Video eliminado correctamente"}), 200

    except Exception as e:
        print(f"Error en /delete-video: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500

@app.route('/get-videos', methods=['GET'])
def get_videos():
    try:
        videos = Video.query.all()
        video_list = [{'video_id': video.video_id} for video in videos]
        return jsonify(video_list)
    except Exception as e:
        print(f"Error en /get-videos: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500

@socketio.on('solicitar_videos')
def handle_solicitar_videos():
    """Enviar lista de videos al cliente en tiempo real"""
    try:
        db_videos = Video.query.all()
        db_videos_data = [{'video_id': video.video_id} for video in db_videos]
        emit('actualizar_videos', db_videos_data)
    except Exception as e:
        print(f"Error al manejar evento solicitar_videos: {e}")
        emit('error', {'message': "Error al obtener videos"})

@app.route('/visitor')
def visitor():
    """Página para visitantes: permite interactuar con los videos y usar el formulario de casting."""
    try:
        db_videos = Video.query.all()
        return render_template('visitor.html', db_videos=db_videos)

    except Exception as e:
        print(f"Error al cargar la página de visitantes: {e}")
        return jsonify({"success": False, "message": "Error al cargar la página"}), 500

@app.route('/submit-casting', methods=['POST'])
def submit_casting():
    """Procesa el formulario de casting."""
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        description = request.form.get('description')
        youtube_link = request.form.get('youtube_link')

        if not all([name, email, description, youtube_link]):
            return jsonify({"success": False, "message": "Todos los campos son obligatorios"}), 400

        msg = Message("Nueva postulación",
                      recipients=["admin@oneder.com"])  # Cambia por el correo del administrador
        msg.body = f"""
        Nombre: {name}
        Email: {email}
        Descripción: {description}
        Enlace de YouTube: {youtube_link}
        """
        mail.send(msg)

        return jsonify({"success": True, "message": "Postulación enviada correctamente"}), 200

    except Exception as e:
        print(f"Error en /submit-casting: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500

if __name__ == '__main__':
    socketio.run(app, debug=True)
