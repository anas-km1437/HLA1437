from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_anas_1437'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_pro_v4.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Models
class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    background = db.Column(db.String(500), default="")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    content = db.Column(db.String(500))
    file = db.Column(db.String(200))
    file_type = db.Column(db.String(20))
    reply_to = db.Column(db.String(500))
    time = db.Column(db.String(20))

online_users = {} 

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    if Room.query.filter_by(name=data['name']).first():
        return {"msg": "اسم الغرفة مستخدم مسبقاً", "status": "error"}
    bg = data.get('background', '')
    db.session.add(Room(name=data['name'], password=data['password'], background=bg))
    db.session.commit()
    return {"msg": "تم إنشاء الغرفة بنجاح", "status": "success"}

@app.route('/update_bg', methods=['POST'])
def update_bg():
    data = request.json
    room = Room.query.filter_by(name=data['room'], password=data['password']).first()
    if room:
        room.background = data['bg_url']
        db.session.commit()
        socketio.emit('bg_updated', data['bg_url'], to=data['room'])
        return {"msg": "تم تحديث الخلفية للجميع"}
    return {"msg": "خطأ في الصلاحيات", "status": "error"}

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
    room_name = data['room']
    r = Room.query.filter_by(name=room_name, password=data['password']).first()
    if not r:
        emit('error_msg', "بيانات الغرفة خاطئة")
        return
    join_room(room_name)
    if room_name not in online_users: online_users[room_name] = {}
    online_users[room_name][request.sid] = data['username']
    emit('join_status', {'status': 'success', 'bg': r.background})
    emit('update_users', list(online_users[room_name].values()), to=room_name)
    msgs = Message.query.filter_by(room=room_name).all()
    for m in msgs:
        emit('message', {"username": m.username, "msg": m.content, "file": m.file, "file_type": m.file_type, "reply_to": m.reply_to, "time": m.time})

@socketio.on('message')
def handle_message(data):
    f_type = None
    if data.get('file'):
        ext = data['file'].split('.')[-1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif']: f_type = 'image'
        elif ext in ['mp4', 'webm']: f_type = 'video'
        else: f_type = 'audio'
    timestamp = datetime.now().strftime("%I:%M %p")
    db.session.add(Message(room=data['room'], username=data['username'], content=data.get('msg'), file=data.get('file'), file_type=f_type, reply_to=data.get('reply_to'), time=timestamp))
    db.session.commit()
    data['time'] = timestamp
    data['file_type'] = f_type
    emit('message', data, to=data['room'])

@socketio.on('disconnect')
def disconnect():
    for room, users in online_users.items():
        if request.sid in users:
            del users[request.sid]
            emit('update_users', list(users.values()), to=room)
            break

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    socketio.run(app, host='0.0.0.0', port=10000)
