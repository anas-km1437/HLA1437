from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat_secret_123'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(500))
    file = db.Column(db.String(200))
    file_type = db.Column(db.String(20))
    reply_to = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

online_users = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    name, password = data.get('name'), data.get('password')
    if Room.query.filter_by(name=name).first():
        return {"msg": "اسم الغرفة مستخدم فعلاً", "status": "error"}
    db.session.add(Room(name=name, password=password))
    db.session.commit()
    return {"msg": "تم إنشاء الغرفة بنجاح", "status": "success"}

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    chunk = request.files['chunk']
    filename = request.form['filename']
    chunk_index = int(request.form['index'])
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    mode = 'ab' if chunk_index > 0 else 'wb'
    with open(filepath, mode) as f:
        f.write(chunk.read())
    return "ok"

@socketio.on('join')
def join(data):
    room = data.get('room')
    username = data.get('username')
    password = data.get('password')
    
    r = Room.query.filter_by(name=room, password=password).first()
    
    if not r:
        # إرسال حدث خطأ مخصص للمستخدم الذي حاول الدخول فقط
        emit('join_error', {'msg': 'اسم الغرفة أو كلمة السر خطأ!'})
        return

    join_room(room)
    if room not in online_users: online_users[room] = {}
    online_users[room][request.sid] = username

    # إخبار الواجهة أن الدخول تم بنجاح
    emit('join_success', {'username': username, 'room': room})

    msgs = Message.query.filter_by(room=room).order_by(Message.timestamp.asc()).all()
    history = [{
        "username": m.username,
        "msg": m.content,
        "file": m.file,
        "file_type": m.file_type,
        "reply_to": m.reply_to,
        "time": m.timestamp.strftime("%I:%M %p")
    } for m in msgs]
    
    emit('history', history)

@socketio.on('message')
def handle_message(data):
    room = data.get('room')
    if not room: return

    f_type = None
    if data.get('file'):
        ext = data['file'].split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif']: f_type = 'image'
        elif ext in ['mp4', 'webm']: f_type = 'video'
        elif ext in ['webm', 'mp3', 'wav', 'ogg']: f_type = 'audio'

    new_msg = Message(
        room=room,
        username=data['username'],
        content=data.get('msg'),
        file=data.get('file'),
        file_type=f_type,
        reply_to=data.get('reply_to'),
        timestamp=datetime.now()
    )
    db.session.add(new_msg)
    db.session.commit()

    data['time'] = new_msg.timestamp.strftime("%I:%M %p")
    data['file_type'] = f_type
    emit('message', data, to=room)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, host='0.0.0.0', port=10000)
