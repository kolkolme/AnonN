# forum.py
from flask import Flask, request, redirect, render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import html
import click

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'super-secret-key'
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    replies = db.relationship('Reply', backref='post', lazy=True)

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)

# Утилиты
def escape_html(text):
    return html.escape(text).replace('\n', '<br>')

base_html = lambda content: f'''
<!DOCTYPE html>
<html>
<head>
    <title>Анонимный форум</title>
    <style>
        body {{ max-width: 800px; margin: 0 auto; padding: 20px; font-family: Arial, sans-serif; }}
        .post {{ border: 1px solid #ccc; padding: 15px; margin: 10px 0; }}
        .admin-panel {{ background: #f0f0f0; padding: 10px; margin: 20px 0; }}
        textarea {{ width: 100%; height: 100px; }}
        .reply {{ margin-left: 30px; margin-top: 10px; }}
        .time {{ color: #666; font-size: 0.9em; }}
        .auth-links {{ float: right; }}
    </style>
</head>
<body>
    <h1>Анонимный форум <div class="auth-links">
        {'<a href="/logout">Выйти</a>' if current_user.is_authenticated else '<a href="/login">Вход</a> | <a href="/register">Регистрация</a>'}
    </div></h1>
    {content}
</body>
</html>
'''

# Роуты
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        content = request.form['content']
        new_post = Post(content=content)
        db.session.add(new_post)
        db.session.commit()
        return redirect('/')
    
    posts = Post.query.order_by(Post.date.desc()).all()
    posts_html = []
    for post in posts:
        replies_html = ''.join(
            f'<div class="reply">{escape_html(reply.content)}<div class="time">{reply.date.strftime("%Y-%m-%d %H:%M")}</div></div>'
            for reply in post.replies
        )
        
        delete_btn = ''
        if current_user.is_authenticated and current_user.is_admin:
            delete_btn = f'<form method="POST" action="/delete_post/{post.id}"><button type="submit">Удалить</button></form>'
        
        posts_html.append(f'''
            <div class="post">
                {delete_btn}
                <div>{escape_html(post.content)}</div>
                <div class="time">{post.date.strftime("%Y-%m-%d %H:%M")}</div>
                <form method="POST" action="/reply/{post.id}">
                    <textarea name="content" required></textarea>
                    <button type="submit">Ответить</button>
                </form>
                {replies_html}
            </div>
        ''')
    
    admin_panel = ''
    if current_user.is_authenticated and current_user.is_admin:
        admin_panel = '''
        <div class="admin-panel">
            <h3>Админ-панель</h3>
            <form method="POST" action="/admin_delete">
                <input type="number" name="post_id" placeholder="ID поста" required>
                <button type="submit">Удалить пост</button>
            </form>
        </div>
        '''
    
    return render_template_string(base_html(f'''
        {admin_panel}
        <form method="POST">
            <textarea name="content" placeholder="Новое сообщение..." required></textarea>
            <button type="submit">Отправить</button>
        </form>
        <h2>Сообщения ({len(posts)})</h2>
        {''.join(posts_html)}
    '''))

@app.route('/reply/<int:post_id>', methods=['POST'])
def reply(post_id):
    content = request.form['content']
    new_reply = Reply(content=content, post_id=post_id)
    db.session.add(new_reply)
    db.session.commit()
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            login_user(user)
            return redirect('/')
        return 'Неверные данные'
    return render_template_string(base_html('''
        <form method="POST">
            <input type="text" name="username" placeholder="Логин" required><br>
            <input type="password" name="password" placeholder="Пароль" required><br>
            <button type="submit">Войти</button>
        </form>
    '''))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form['password'])
        new_user = User(username=request.form['username'], password_hash=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        return redirect('/login')
    return render_template_string(base_html('''
        <form method="POST">
            <input type="text" name="username" placeholder="Логин" required><br>
            <input type="password" name="password" placeholder="Пароль" required><br>
            <button type="submit">Зарегистрироваться</button>
        </form>
    '''))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    if current_user.is_admin:
        post = Post.query.get(post_id)
        if post:
            Reply.query.filter_by(post_id=post_id).delete()
            db.session.delete(post)
            db.session.commit()
    return redirect('/')

# CLI команды
@app.cli.command("create-admin")
@click.argument("username")
@click.argument("password")
def create_admin(username, password):
    hashed_pw = generate_password_hash(password)
    admin = User(username=username, password_hash=hashed_pw, is_admin=True)
    db.session.add(admin)
    db.session.commit()
    print(f"Админ {username} создан")

@app.cli.command("delete-post")
@click.argument("post_id")
def cli_delete_post(post_id):
    post = Post.query.get(post_id)
    if post:
        Reply.query.filter_by(post_id=post_id).delete()
        db.session.delete(post)
        db.session.commit()
        print(f"Пост {post_id} удален")
    else:
        print("Пост не найден")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)