from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit
from werkzeug.security import check_password_hash, generate_password_hash
import os
from flask_cors import CORS

# Configuración de la aplicación Flask
app = Flask(
    __name__,
    template_folder=os.path.join(os.getcwd(), 'public_html'),
    static_folder=os.path.join(os.getcwd(), 'public_html', 'assets')
)

# Configuración de la base de datos
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Cambia según tu configuración
app.config['MYSQL_DB'] = 'oneder_site'

# Configuración de correo (Flask-Mail)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # Tu correo
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # Contraseña
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')  # Remitente

# Inicializar extensiones
mysql = MySQL(app)
mail = Mail(app)
socketio = SocketIO(app)  # Inicializar SocketIO
CORS(app)  # Manejar solicitudes CORS si es necesario

# Clave secreta para manejar sesiones
app.secret_key = os.getenv("FLASK_SECRET_KEY", "mi_clave_secreta")

# Datos de usuario permitidos
ALLOWED_EMAIL = "bellwhite183@gmail.com"
ALLOWED_PASSWORD = "HOLA1234"  # Cambiar según sea necesario


@app.route('/')
def home():
    """Renderiza la página principal con videos de la base de datos y de YouTube."""
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT video_id FROM videos")
        db_videos = [video[0] for video in cursor.fetchall()]
        cursor.close()

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

        if email == ALLOWED_EMAIL and password == ALLOWED_PASSWORD:
            session['user_id'] = email

            try:
                msg = Message("Nuevo inicio de sesión",
                              recipients=["bellwhite183@gmail.com"])
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

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM videos WHERE video_id = %s", (video_id,))
        existing_video = cursor.fetchone()

        if existing_video:
            return jsonify({"success": False, "message": "Este video ya está en la base de datos"}), 400

        cursor.execute("INSERT INTO videos (video_id) VALUES (%s)", (video_id,))
        mysql.connection.commit()
        cursor.close()

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

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM videos WHERE video_id = %s", (video_id,))
        video_to_delete = cursor.fetchone()

        if not video_to_delete:
            return jsonify({"success": False, "message": "El video no existe en la base de datos"}), 404

        cursor.execute("DELETE FROM videos WHERE video_id = %s", (video_id,))
        mysql.connection.commit()
        cursor.close()

        socketio.emit('eliminar_video', {'video_id': video_id})
        return jsonify({"success": True, "message": "Video eliminado correctamente"}), 200

    except Exception as e:
        print(f"Error en /delete-video: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500

@app.route('/get-videos', methods=['GET'])
def get_videos():
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT video_id FROM videos")
        videos = [{'video_id': row[0]} for row in cursor.fetchall()]
        cursor.close()
        return jsonify(videos)
    except Exception as e:
        print(f"Error en /get-videos: {e}")
        return jsonify({"success": False, "message": "Error interno del servidor"}), 500


@socketio.on('solicitar_videos')
def handle_solicitar_videos():
    """Enviar lista de videos al cliente en tiempo real"""
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT video_id FROM videos")
        db_videos = [{'video_id': video[0]} for video in cursor.fetchall()]
        cursor.close()
        emit('actualizar_videos', db_videos)
    except Exception as e:
        print(f"Error al manejar evento solicitar_videos: {e}")
        emit('error', {'message': "Error al obtener videos"})

@app.route('/visitor')
def visitor():
    """Página para visitantes: permite interactuar con los videos y usar el formulario de casting."""
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT video_id FROM videos")
        db_videos = [video[0] for video in cursor.fetchall()]
        cursor.close()

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

        # Aquí podrías guardar los datos en la base de datos o enviarlos por correo.
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
