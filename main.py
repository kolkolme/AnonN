from flask import Flask, request, redirect, url_for, render_template_string, flash, jsonify, \
    get_flashed_messages
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import html
import os
import re
from sqlalchemy import func, or_

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-very-secret-key-change-me-in-prod')
# Changed DB name for this major feature
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///forum_v17_reports_design.db' # Updated DB name
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Пожалуйста, войдите, чтобы получить доступ к этой странице."
login_manager.login_message_category = "info"

# --- Models ---

post_tags = db.Table('post_tags',
                     db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
                     db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
                     )


class UserAchievement(db.Model):
    __tablename__ = 'user_achievement'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), primary_key=True)
    awarded_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='user_achievements_association')
    achievement = db.relationship('Achievement', back_populates='user_associations')


class Achievement(db.Model):
    __tablename__ = 'achievement'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=False)
    icon_emoji = db.Column(db.String(10), nullable=False)
    condition_type = db.Column(db.String(50), nullable=False)
    condition_value = db.Column(db.Integer, nullable=False)

    user_associations = db.relationship('UserAchievement', back_populates='achievement', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Achievement {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    about_me = db.Column(db.Text, nullable=True, default='')  # New field for user profile
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)

    posts = db.relationship('Post', backref='author', lazy='dynamic')
    replies = db.relationship('Reply', backref='author', lazy='dynamic')
    votes = db.relationship('Vote', backref='voter', lazy='dynamic', cascade="all, delete-orphan")

    user_achievements_association = db.relationship('UserAchievement', back_populates='user',
                                                    cascade="all, delete-orphan")

    # Relationships for direct messages
    sent_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.sender_id', backref='sender',
                                    lazy='dynamic', cascade="all, delete-orphan")
    received_messages = db.relationship('DirectMessage', foreign_keys='DirectMessage.receiver_id', backref='receiver',
                                        lazy='dynamic', cascade="all, delete-orphan")

    # Relationships for reports (new)
    reported_by_others = db.relationship('Report', foreign_keys='Report.reported_user_id', backref='reported_user', lazy='dynamic', cascade="all, delete-orphan")
    reports_made = db.relationship('Report', foreign_keys='Report.reporter_id', backref='reporter', lazy='dynamic', cascade="all, delete-orphan")


    @property
    def achievements(self):
        return [ua.achievement for ua in self.user_achievements_association]

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return not self.is_banned

    def __repr__(self):
        return f'<User {self.username}>'


class Tag(db.Model):
    __tablename__ = 'tag'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    def __repr__(self):
        return f'<Tag {self.name}>'


class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    pinned = db.Column(db.Boolean, default=False)
    last_edited_at = db.Column(db.DateTime, nullable=True)
    edit_count = db.Column(db.Integer, default=0)

    replies = db.relationship('Reply', backref='post', lazy='dynamic', cascade="all, delete-orphan")
    tags = db.relationship('Tag', secondary=post_tags, lazy='subquery',
                           backref=db.backref('posts', lazy='dynamic'))
    votes = db.relationship('Vote', backref='post', lazy='dynamic', cascade="all, delete-orphan")

    @property
    def score(self):
        likes = self.votes.filter_by(vote_type=1).count()
        dislikes = self.votes.filter_by(vote_type=-1).count()
        return likes - dislikes

    def __repr__(self):
        return f'<Post {self.id} by User {self.user_id}>'


class Reply(db.Model):
    __tablename__ = 'reply'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f'<Reply {self.id} to Post {self.post_id} by User {self.user_id}>'


class Vote(db.Model):
    __tablename__ = 'vote'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    vote_type = db.Column(db.Integer, nullable=False)  # 1 for like, -1 for dislike
    date = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'post_id', name='uq_user_post_vote'),)

    def __repr__(self):
        return f'<Vote {self.vote_type} by User {self.user_id} for Post {self.post_id}>'


class DirectMessage(db.Model):
    __tablename__ = 'direct_message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_read = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<DirectMessage from {self.sender_id} to {self.receiver_id} at {self.timestamp}>'

# New Report Model
class Report(db.Model):
    __tablename__ = 'report'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reported_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.Text, nullable=True) # Reason can be optional
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_resolved = db.Column(db.Boolean, default=False) # To track if admin has reviewed

    def __repr__(self):
        return f'<Report {self.id} by {self.reporter_id} on {self.reported_user_id}>'


# --- Achievement Logic ---
def check_and_award_achievements(user, event_type, event_context=None):
    if not user or not user.is_authenticated:
        return

    awarded_new = False
    user_achievement_ids = {ua.achievement_id for ua in user.user_achievements_association}
    all_achievements = Achievement.query.all()

    for ach in all_achievements:
        if ach.id in user_achievement_ids:
            continue
        awarded_this_check = False
        if ach.condition_type == 'posts_made' and user.posts.count() >= ach.condition_value:
            awarded_this_check = True
        elif ach.condition_type == 'votes_cast' and user.votes.count() >= ach.condition_value:
            awarded_this_check = True
        elif ach.condition_type == 'total_post_upvotes_received':
            if event_type == 'vote_on_my_post' and event_context and event_context.get('post_author_id') == user.id:
                total_upvotes = db.session.query(func.count(Vote.id)) \
                                    .join(Post, Vote.post_id == Post.id) \
                                    .filter(Post.user_id == user.id, Vote.vote_type == 1) \
                                    .scalar() or 0
                if total_upvotes >= ach.condition_value: awarded_this_check = True
        elif ach.condition_type == 'post_score_reached':
            if event_type == 'vote_on_my_post' and event_context and event_context.get('post_user_id') == user.id:
                target_post_id = event_context.get('post_id')
                if target_post_id:
                    target_post = Post.query.get(target_post_id)
                    if target_post and target_post.score >= ach.condition_value:
                        awarded_this_check = True

        if awarded_this_check:
            new_user_ach = UserAchievement(user_id=user.id, achievement_id=ach.id)
            db.session.add(new_user_ach)
            user_achievement_ids.add(ach.id)  # Avoid re-awarding in same check cycle
            awarded_new = True
            flash(f'Новое достижение разблокировано: {ach.name} ({ach.icon_emoji})!', 'success')
            app.logger.info(f"User {user.username} awarded achievement: {ach.name}")
    if awarded_new:
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error committing new achievements for user {user.username}: {e}")


@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


def escape_html(text):
    if text is None: return ""
    return html.escape(text).replace('\n', '<br>')


def render_formatted_post_content(text):
    if text is None: return ""
    escaped_text = html.escape(text)
    simple_replacements = {"&lt;b&gt;": "<b>", "&lt;/b&gt;": "</b>", "&lt;i&gt;": "<i>", "&lt;/i&gt;": "</i>",
                           "&lt;u&gt;": "<u>", "&lt;/u&gt;": "</u>", "&lt;/font&gt;": "</font>"}
    for old, new in simple_replacements.items():
        escaped_text = escaped_text.replace(old, new)

    def replace_font_tag(match):
        color_value = match.group(1)
        if re.fullmatch(r"#(?:[0-9a-fA-F]{3}){1,2}|[a-zA-Z]+", color_value):
            return f'<font color="{html.escape(color_value)}">'
        return match.group(0)  # Return original if color format is invalid

    escaped_text = re.sub(r'&lt;font color=&quot;([a-zA-Z0-9#]+?)&quot;&gt;', replace_font_tag, escaped_text)
    return escaped_text.replace('\n', '<br>')


def render_post(post):
    with app.app_context():
        is_authenticated = current_user and current_user.is_authenticated
        user_id = current_user.id if is_authenticated else None
        is_admin = current_user.is_admin if is_authenticated else False

        author_username_html = escape_html(post.author.username if post.author else 'Аноним')
        if post.author:
            author_username_html = f'<a href="{url_for('user_profile', username=post.author.username)}">{author_username_html}</a>'

        replies = post.replies.order_by(Reply.date.asc()).all()
        replies_html = ''.join(
            f'''<div class="reply" id="reply-{reply.id}">
                   <div class="reply-content">{escape_html(reply.content)}</div>
                   <div class="metadata">
                       <div>
                         <span class="author"><a href="{url_for('user_profile', username=reply.author.username)}">{escape_html(reply.author.username)}</a></span>
                         <span class="time">{reply.date.strftime("%Y-%m-%d %H:%M")}</span>
                       </div>
                       <div>
                         {'<form method="POST" action="' + url_for('delete_reply', reply_id=reply.id) + '" style="display:inline;"><button type="submit" class="delete-button">Удалить</button></form>' if is_authenticated and (is_admin or reply.user_id == user_id) else ''}
                         {''  # Ban/unban buttons removed from here
            }
                       </div>
                   </div>
               </div>'''
            for reply in replies
        )

        tags_html = ''
        if post.tags:
            current_sort_by = request.args.get('sort_by', 'date_desc') if request else 'date_desc'
            tags_html = '<div class="post-tags">Теги: ' + ', '.join(
                [f'<a href="{url_for('index', tag=tag.name, sort_by=current_sort_by)}">{escape_html(tag.name)}</a>' for
                 tag in post.tags]) + '</div>'

        score = post.score
        score_class = 'score-neutral'
        if score > 0:
            score_class = 'score-positive'
        elif score < 0:
            score_class = 'score-negative'

        user_vote = None
        if is_authenticated:
            vote_obj = post.votes.filter_by(user_id=user_id).first()
            if vote_obj: user_vote = vote_obj.vote_type

        like_active_class = 'active' if user_vote == 1 else ''
        dislike_active_class = 'active' if user_vote == -1 else ''

        edit_indicator_html = ''
        if post.edit_count > 0:
            last_edit_time_str = post.last_edited_at.strftime("%Y-%m-%d %H:%M") if post.last_edited_at else "N/A"
            edit_indicator_html = f'<span class="edit-indicator" title="Последнее изменение: {last_edit_time_str}">(изменено {post.edit_count} раз)</span>'

        edit_button_html = ''
        if is_authenticated and (is_admin or post.user_id == user_id):
            edit_button_html = f'<a href="{url_for('edit_post', post_id=post.id)}" class="button edit-button-link">Изменить</a>'

        post_content_html = render_formatted_post_content(post.content)

        # Achievements are now shown on profile page, not next to username in post
        # author_achievements_html = ''
        # if post.author and post.author.user_achievements_association:
        #     for ua in post.author.user_achievements_association:
        #         author_achievements_html += f'<span class="achievement-icon" title="{escape_html(ua.achievement.name)}: {escape_html(ua.achievement.description)}">{ua.achievement.icon_emoji}</span>'

        return f'''
            <div class="post" id="post-{post.id}" data-post-id="{post.id}">
                <div class="post-header">
                     <div>
                        {'<span class="pinned-indicator">ЗАКРЕПЛЕНО</span>' if post.pinned else ''}
                        <span class="author">{author_username_html}</span>
                        <span class="time">{post.date.strftime("%Y-%m-%d %H:%M")}</span>
                        {edit_indicator_html}
                     </div>
                     <div class="post-actions">
                        {edit_button_html}
                        {'<form method="POST" action="' + url_for('delete_post', post_id=post.id) + '" style="display:inline;"><button type="submit" class="delete-button">Удалить пост</button></form>' if is_authenticated and (is_admin or post.user_id == user_id) else ''}
                        {''  # Ban/unban buttons removed from here
        }
                     </div>
                </div>
                <div class="post-content">{post_content_html}</div>
                {tags_html}
                <div class="vote-section">
                    <button class="vote-button like-button {like_active_class}" data-post-id="{post.id}" data-vote-type="like" {'disabled' if not is_authenticated else ''}>Согласен 👍</button>
                    <span id="score-{post.id}" class="post-score {score_class}">{score}</span>
                    <button class="vote-button dislike-button {dislike_active_class}" data-post-id="{post.id}" data-vote-type="dislike" {'disabled' if not is_authenticated else ''}>Не согласен 👎</button>
                </div>
                <form method="POST" action="{url_for('reply', post_id=post.id)}"><textarea name="content" placeholder="Ваш ответ..." required rows="2"></textarea><button type="submit">Ответить</button></form>
                {replies_html}
            </div>
        '''


BASE_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AnonN</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0d0d0d;
            --text-color: #e0e0e0;
            --border-color: #333333;
            --input-bg: #1a1a1a;
            --input-border: #444444;
            --button-bg: #2a2a2a;
            --button-text: #f0f0f0;
            --button-hover-bg: #3a3a3a;
            --link-color: #aaaaaa;
            --link-hover-color: #cccccc;
            --time-color: #777777;
            --post-bg: #1f1f1f;
            --reply-bg: #252525;
            --flash-info-bg: #2a3a4a;
            --radius-full: 35px;
            --radius-large-container: 1.5rem;
            --pinned-color: #ffcc00;
            --dm-sidebar-bg: #161616;
            --dm-active-conversation-bg: #252525;
            --dm-message-sent-bg: #2a3a4a;
            --dm-message-received-bg: #3a3a3a;
            --toggle-button-bg: #4a4a4a;
            --toggle-button-hover-bg: #5a5a5a;
            --left-sidebar-width: 520px;
            --bottom-panel-height-approx: 250px;
            --profile-header-bg: #252525;
            --achievement-bg: #2c2c2c;
            --ban-button-bg: #c0392b;
            --unban-button-bg: #27ae60;
            --button-hover-danger-bg: #e74c3c;
            --button-hover-success-bg: #2ecc71;
            --report-button-bg: #e67e22; /* Orange-ish for report */
            --report-button-hover-bg: #d35400;
        }
        body {
            font-family: 'Montserrat', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            margin: 0;
            padding: 0;
            display: flex;
            min-height: 100vh;
            overflow-x: hidden;
        }

        .messaging-sidebar {
            width: var(--left-sidebar-width);
            min-width: var(--left-sidebar-width);
            background-color: var(--dm-sidebar-bg);
            border-right: 1px solid var(--border-color);
            padding: 15px;
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            overflow-y: auto;
            height: 100vh;
            position: fixed;
            left: 0;
            top: 0;
            transition: transform 0.3s ease-in-out, min-width 0.3s ease-in-out, width 0.3s ease-in-out;
            z-index: 1001;
            border-top-right-radius: 60px;
            border-bottom-right-radius: 60px;
        }
        .messaging-sidebar.collapsed {
            transform: translateX(-100%);
            min-width: 0;
            width: 0;
            padding-left: 0;
            padding-right: 0;
            border-right: none;
        }

        .main-forum-container {
            flex-grow: 1;
            padding: 20px;
            margin-left: var(--left-sidebar-width);
            box-sizing: border-box;
            transition: margin-left 0.3s ease-in-out, max-width 0.3s ease-in-out;
        }
        .main-forum-container.left-sidebar-collapsed {
            margin-left: 0;
        }

        .main-content-wrapper {
            max-width: 800px;
            margin: 0 auto;
            padding-bottom: var(--bottom-panel-height-approx);
            transition: padding-bottom 0.3s ease-in-out;
        }
        .main-content-wrapper.bottom-panel-collapsed {
            padding-bottom: 40px;
        }


        h1, h2 {
            color: var(--text-color);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            margin-top: 30px;
            font-weight: 600;
        }
        h1 { border-bottom: none; text-align: center; margin-bottom: 40px; font-weight: 700; }
        h1 a { color: var(--text-color); text-decoration: none; }
        a { color: var(--link-color); text-decoration: none; transition: color 0.2s; }
        a:hover { color: var(--link-hover-color); text-decoration: none; }

        form { margin-bottom: 30px; padding: 25px; border: 1px solid var(--border-color); background-color: var(--post-bg); border-radius: var(--radius-large-container); }

        textarea, input[type="text"], input[type="password"], input[type="email"] { width: 100%; padding: 12px 18px; margin-bottom: 15px; border: 1px solid var(--input-border); background-color: var(--input-bg); color: var(--text-color); border-radius: var(--radius-full); font-size: 1em; box-sizing: border-box; transition: border-color 0.2s, background-color 0.2s; font-family: 'Montserrat', sans-serif; }
        textarea:focus, input[type="text"]:focus, input[type="password"]:focus, input[type="email"]:focus { outline: none; border-color: var(--link-color); background-color: #222; }
        textarea { min-height: 100px; resize: vertical; }
        button[type="submit"], .button { padding: 10px 20px; background-color: var(--button-bg); color: var(--button-text); border: none; border-radius: var(--radius-full); cursor: pointer; font-size: 0.95em; font-weight: 500; transition: background-color 0.2s; display: inline-block; font-family: 'Montserrat', sans-serif; margin-right: 5px; text-decoration: none; }
        button[type="submit"]:hover, .button:hover { background-color: var(--button-hover-bg); }
        .button.report-button { background-color: var(--report-button-bg); }
        .button.report-button:hover { background-color: var(--report-button-hover-bg); }


        .post { border: 1px solid var(--border-color); padding: 20px 25px; margin-bottom: 25px; background-color: var(--post-bg); border-radius: var(--radius-large-container); overflow-wrap: break-word; word-wrap: break-word; }
        .reply { margin-left: 0; margin-top: 15px; padding: 15px 20px; background-color: var(--reply-bg); border: 1px solid var(--border-color); border-radius: var(--radius-large-container); }
        .post-content, .reply-content { margin-bottom: 15px; }
        .metadata { color: var(--time-color); font-size: 0.85em; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 10px; }
        .author { font-weight: 600; margin-right: 10px; color: var(--text-color); }
        .achievement-icon { margin-left: 4px; cursor: help; font-size: 0.9em; }
        .post form { margin-top: 25px; }
        .post-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px;}
        .post-tags { font-size: 0.8em; color: var(--link-color); margin-top: 5px; margin-bottom: 10px; }
        .pinned-indicator { color: var(--pinned-color); font-weight: bold; }
        .edit-indicator { font-size: 0.8em; color: var(--edit-indicator-color); cursor: default; }
        .vote-section { display: flex; align-items: center; gap: 10px; margin-top: 15px; }
        .vote-button { background-color: var(--button-bg); color: var(--button-text); border: none; border-radius: var(--radius-full); padding: 6px 12px; cursor: pointer; font-size: 0.85em; transition: background-color 0.2s; }
        .vote-button:hover { background-color: var(--button-hover-bg); }
        .vote-button.active { background-color: var(--link-color); } /* Adjusted active vote button color */
        .post-score { font-weight: bold; font-size: 0.9em; min-width: 20px; text-align: center; }
        .score-positive { color: #2ecc71; } /* Green */
        .score-negative { color: #e74c3c; } /* Red */
        .score-neutral { color: var(--text-color); }

        .header { display: flex; justify-content: flex-end; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color); }
        .nav a, .nav span { margin-left: 15px; font-size: 0.9em; }
        .nav .username-link { font-weight: bold; }
        .sort-options { margin-bottom: 20px; font-size: 0.9em; display: flex; flex-wrap: wrap; align-items: center; gap: 15px; }
        .flash-messages { list-style: none; padding: 0; margin: 0 0 20px 0; }
        .flash-messages li { padding: 12px 18px; margin-bottom: 12px; border-radius: var(--radius-full); text-align: center; font-weight: 500; }
        .flash-info { color: #3498db; background-color: #dbe9f3; border: 1px solid #a6cbe7; } /* Light blue */
        .flash-success { color: #27ae60; background-color: #d4edda; border: 1px solid #c3e6cb; } /* Light green */
        .flash-error { color: #c0392b; background-color: #f8d7da; border: 1px solid #f5c6cb; } /* Light red */

        /* Combined New Post Panel */
        .fixed-bottom-new-post-panel {
            position: fixed;
            bottom: 0;
            left: 720px; /* Adjusted to use variable */
            right: 200px;
            background-color: rgba(31, 31, 31, 0.85);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            padding: 15px 20px;
            border-top: 1px solid var(--border-color);
            z-index: 1000;
            border-top-left-radius: 60px; /* Smaller radius */
            border-top-right-radius: 60px; /* Smaller radius */
            box-shadow: 0 -5px 25px rgba(0,0,0,0.35);
            box-sizing: border-box;
            transition: transform 0.3s ease-in-out, max-height 0.3s ease-in-out, padding 0.3s ease-in-out, border-top-width 0.3s ease-in-out, left 0.3s ease-in-out;
            max-height: var(--bottom-panel-height-approx);
            overflow: hidden; /* Hide content when collapsed */
            display: flex; /* Use flexbox */
            flex-direction: column; /* Stack elements vertically */
            margin-left: 200px;
        }

        .fixed-bottom-new-post-panel.left-sidebar-collapsed {
             left: 0; /* Adjust left when sidebar is collapsed */
        }

        .fixed-bottom-new-post-panel.collapsed {
            max-height: 0 !important;
            padding-top: 0 !important;
            padding-bottom: 0 !important;
            border-top-width: 0 !important;
        }

        .fixed-bottom-new-post-panel form {
            margin-bottom: 0;
            border: none;
            background-color: transparent;
            padding: 0;
            display: flex; /* Use flexbox */
            flex-direction: column; /* Stack elements vertically */
            height: 100%; /* Fill panel height */
        }

        .fixed-bottom-new-post-panel textarea {
            flex-grow: 1; /* Allow textarea to grow */
            min-height: 60px; /* Minimum height */
            margin-bottom: 8px !important;
            padding: 10px 15px !important;
            font-size: 0.95em !important;
            resize: vertical; /* Allow vertical resize */
            border-radius: var(--radius-full);
        }

        .fixed-bottom-new-post-panel input[type="text"] {
             margin-bottom: 8px !important;
             padding: 10px 15px !important;
             font-size: 0.95em !important;
             border-radius: var(--radius-full);
        }

        .fixed-bottom-new-post-panel .controls-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 5px;
            flex-shrink: 0; /* Prevent shrinking */
            border-radius: var(--radius-full);
        }

        .fixed-bottom-new-post-panel .pinned-checkbox-container {
            display: flex;
            align-items: center;
            border-radius: var(--radius-full);
        }

        .fixed-bottom-new-post-panel button[type="submit"] {
            padding: 8px 18px !important;
            font-size: 0.9em !important;
            border-radius: var(--radius-full);
        }

        .fixed-bottom-new-post-panel .checkbox-label {
            font-size: 0.9em;
            margin-bottom: 0;
            font-weight: 400;
            border-radius: var(--radius-full);
        }

        .color-picker-container {
            display: flex;
            align-items: center;
            margin-bottom: 8px; /* Space below color picker */
            gap: 10px;
            border-radius: var(--radius-full);
        }

        .color-picker-container label {
             font-size: 0.9em;
             color: var(--time-color);
             border-radius: var(--radius-full);
        }

        .color-picker-container input[type="color"] {
            padding: 0;
            border: none;
            background: none;
            height: 30px;
            width: 40px;
            cursor: pointer;
            border-radius: var(--radius-full);
        }
         .color-picker-container button {
             padding: 8px 12px;
             font-size: 0.8em;
             border-radius: var(--radius-full);
             border: none;
             background-color: rgba(50, 50, 50, 0.85);
             backdrop-filter: blur(8px);
             -webkit-backdrop-filter: blur(8px);
             color: var(--text-color);
         }


        /* Messaging Sidebar Specific Styles */
        .messaging-sidebar h3 { font-size: 1.1em; color: var(--text-color); margin-top: 0; margin-bottom: 10px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; }
        .messaging-sidebar input[type="text"] { padding: 8px 12px !important; font-size: 0.9em !important; margin-bottom: 10px !important; border-radius: var(--radius-full); }
        .conversation-list, .dm-user-search-results { list-style: none; padding: 0; margin: 0; flex-grow: 1; overflow-y: auto; } /* flex-grow for list */
        .conversation-list li, .dm-user-search-results li { padding: 10px; border-bottom: 1px solid var(--border-color); cursor: pointer; font-size: 0.9em; transition: background-color 0.2s; display: flex; justify-content: space-between; align-items: center; }
        .conversation-list li:hover, .dm-user-search-results li:hover { background-color: var(--button-hover-bg); }
        .conversation-list li.active-conversation { background-color: var(--dm-active-conversation-bg); font-weight: bold; }
        .unread-indicator { display: inline-block; width: 8px; height: 8px; background-color: var(--pinned-color); border-radius: 50%; margin-left: 8px; }
        .chat-area {
            margin-top: 15px;
            border-top: 1px solid var(--border-color);
            padding-top: 15px;
            display: flex;
            flex-direction: column; /* Stack elements */
            flex-grow: 1; /* Allow chat area to fill space */
            overflow: hidden; /* Contain children */
        }
        .chat-header { font-size: 1em; font-weight: bold; margin-bottom:10px; padding-bottom: 5px; border-bottom: 1px #444; flex-shrink: 0; } /* Prevent shrinking */
        .messages-display { flex-grow: 1; overflow-y: auto; margin-bottom: 10px; padding-right: 5px; scroll-behavior: smooth; } /* Allow messages to scroll and grow */
        .message-bubble { padding: 8px 12px; border-radius: 15px; margin-bottom: 8px; max-width: 80%; word-wrap: break-word; font-size: 0.9em; }
        .message-bubble.sent { background-color: var(--dm-message-sent-bg); margin-left: auto; border-bottom-right-radius: 5px; }
        .message-bubble.received { background-color: var(--dm-message-received-bg); margin-right: auto; border-bottom-left-radius: 5px; }
        .message-bubble .msg-time { font-size: 0.7em; color: var(--time-color); display: block; text-align: right; margin-top: 3px; }
        .dm-input-form { flex-shrink: 0; } /* Prevent shrinking */
        .dm-input-form textarea { min-height: 40px !important; padding: 8px 12px !important; font-size: 0.9em !important; margin-bottom: 8px !important; resize: none; border-radius: var(--radius-full); }
        .dm-input-form button { padding: 6px 15px !important; font-size: 0.85em !important; width: 100%; border-radius: var(--radius-full); }
        .no-dm-selected { text-align: center; color: var(--time-color); margin-top: 30px; font-size: 0.9em; flex-grow: 1; display: flex; align-items: center; justify-content: center; } /* Center placeholder */
        #dm-back-to-conversations { font-size: 0.85em; margin-bottom: 10px; cursor: pointer; color: var(--link-color); flex-shrink: 0; } /* Prevent shrinking */
        #dm-back-to-conversations:hover { color: var(--link-hover-color); }
        .dm-user-search-results .user-search-actions { display: flex; gap: 5px; }
        .dm-user-search-results .user-search-actions .button { padding: 5px 10px; font-size: 0.8em; }


        /* Panel Toggle Buttons */
        .panel-toggle-button {
            position: fixed;
            background-color: var(--toggle-button-bg);
            color: var(--button-text);
            border: 1px solid var(--border-color);
            border-radius: 50%;
            width: 36px;
            height: 36px;
            font-size: 18px; /* Consistent font size */
            line-height: 34px;
            text-align: center;
            cursor: pointer;
            z-index: 1005;
            transition: background-color 0.2s, left 0.3s ease-in-out, bottom 0.3s ease-in-out, transform 0.3s ease-in-out;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }
        .panel-toggle-button:hover {
            background-color: var(--toggle-button-hover-bg);
        }

        #left-sidebar-toggle {
            top: 50%;
            left: calc(var(--left-sidebar-width) - 18px);
            transform: translateY(-50%) rotate(0deg); /* No initial rotation */
        }
        #left-sidebar-toggle.collapsed-state {
            left: 5px;
            transform: translateY(-50%) rotate(180deg); /* Rotate when collapsed */
        }
        /* Ensure toggle button position adjusts with sidebar */
        .messaging-sidebar.collapsed + .main-forum-container + #left-sidebar-toggle {
             left: 5px;
        }
         /* Specific rule to handle toggle button when sidebar is collapsed and main container is adjusted */
        .main-forum-container.left-sidebar-collapsed + #left-sidebar-toggle {
             left: 5px;
        }


        #bottom-panel-toggle {
            left: 50%;
            bottom: var(--bottom-panel-height-approx);
            transform: translateX(-50%) translateY(50%);
        }
         #bottom-panel-toggle.collapsed-state {
            bottom: 25px;
            transform: translateX(-50%) translateY(0); /* No vertical translation when collapsed */
        }

        /* User Profile Styles */
        .profile-container { padding: 20px; background-color: var(--post-bg); border-radius: var(--radius-large-container); margin-top: 20px; }
        .profile-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color); flex-wrap: wrap; gap: 15px;} /* Allow wrapping */
        .profile-header h2 { margin: 0; border-bottom: none; flex-grow: 1; } /* Allow title to grow */
        .profile-actions { display: flex; gap: 10px; flex-wrap: wrap; } /* Arrange buttons */
        .profile-actions .button, .profile-actions form button { margin-left: 0; } /* Remove extra margin */
        .profile-actions .report-button { background-color: var(--report-button-bg); } /* Apply report button color */
        .profile-actions .report-button:hover { background-color: var(--report-button-hover-bg); }

        .profile-info { margin-bottom: 20px; }
        .profile-info h3 { margin-top: 0; color: var(--text-color); font-size: 1.2em; }
        .profile-info p { white-space: pre-wrap; word-wrap: break-word; }
        .achievements-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px; }
        .achievement-card { background-color: var(--achievement-bg); padding: 15px; border-radius: 10px; text-align: center; }
        .achievement-card .icon { font-size: 2em; margin-bottom: 5px; }
        .achievement-card .name { font-weight: bold; margin-bottom: 5px; }
        .achievement-card .description { font-size: 0.85em; color: var(--time-color); }
        .ban-button { background-color: var(--ban-button-bg); }
        .ban-button:hover { background-color: var(--button-hover-danger-bg); }
        .unban-button { background-color: var(--unban-button-bg); }
        .unban-button:hover { background-color: var(--button-hover-success-bg); }
        .edit-profile-form textarea { min-height: 150px; }

        /* Report Modal Styles */
        .modal {
            display: none; /* Hidden by default */
            position: fixed; /* Stay in place */
            z-index: 2000; /* Sit on top */
            left: 0;
            top: 0;
            width: 100%; /* Full width */
            height: 100%; /* Full height */
            overflow: auto; /* Enable scroll if needed */
            background-color: rgba(0,0,0,0.6); /* Black w/ opacity */
            backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px);
            padding-top: 60px;
        }

        .modal-content {
            background-color: var(--post-bg);
            margin: 5% auto; /* 15% from the top and centered */
            padding: 20px;
            border: 1px solid var(--border-color);
            width: 80%; /* Could be more responsive */
            max-width: 500px; /* Max width */
            border-radius: var(--radius-large-container);
            position: relative;
        }

        .close-button {
            color: var(--time-color);
            position: absolute;
            top: 10px;
            right: 20px;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }

        .close-button:hover,
        .close-button:focus {
            color: var(--text-color);
            text-decoration: none;
            cursor: pointer;
        }

        .modal-content h3 {
            margin-top: 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
        }

        .modal-content textarea {
            width: calc(100% - 24px); /* Adjust for padding */
            margin-bottom: 15px;
        }

        .modal-content button {
            width: auto; /* Auto width for buttons */
            margin-top: 10px;
        }

         /* Admin Reports Page Styles */
        .admin-reports-container { padding: 20px; background-color: var(--post-bg); border-radius: var(--radius-large-container); margin-top: 20px; }
        .admin-reports-container h2 { margin-top: 0; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 20px;}
        .report-item { border: 1px solid var(--border-color); padding: 15px; margin-bottom: 15px; background-color: var(--reply-bg); border-radius: 10px; }
        .report-item strong { color: var(--text-color); }
        .report-item .report-metadata { font-size: 0.85em; color: var(--time-color); margin-bottom: 10px; }
        .report-item .report-reason { margin-bottom: 10px; white-space: pre-wrap; word-wrap: break-word; }
        .report-item .report-actions { display: flex; gap: 10px; flex-wrap: wrap; }
        .report-item .report-actions form { margin: 0; padding: 0; border: none; background: none; }
        .report-item .report-actions button { padding: 5px 10px; font-size: 0.8em; }
        .report-status-open { color: var(--report-button-bg); font-weight: bold; }
        .report-status-reviewed { color: var(--link-color); }
        .report-status-action_taken { color: var(--unban-button-bg); font-weight: bold; }
        .report-status-dismissed { color: var(--time-color); }


    </style>
</head>
<body>
    <button id="left-sidebar-toggle" class="panel-toggle-button">&laquo;</button>

    <div class="messaging-sidebar" id="messaging-sidebar">
        {% if current_user.is_authenticated %}
            <h3>Сообщения</h3>
            <input type="text" id="dm-user-search" placeholder="Поиск пользователей...">
            <ul id="dm-user-search-results" class="dm-user-search-results"></ul>

            <div id="dm-conversation-list-container" style="flex-grow: 1; overflow-y: auto;"> {# Added flex-grow and overflow #}
                <ul id="dm-conversation-list" class="conversation-list">
                    </ul>
            </div>

            <div id="dm-chat-area-container" class="chat-area" style="display: none;">
                <div id="dm-back-to-conversations">&laquo; К списку диалогов</div>
                <div id="dm-chat-header">Чат с <span id="dm-chat-with-username"></span></div>
                <div id="dm-messages-display" class="messages-display">
                    </div>
                <form id="dm-message-form" class="dm-input-form"> {# Added class #}
                    <input type="hidden" id="dm-receiver-id" name="receiver_id">
                    <textarea id="dm-message-content" name="content" placeholder="Ваше сообщение..." required rows="2"></textarea>
                    <div class="color-picker-container"> {# Added color picker for DM #}
                         <label for="dm-color-picker">Цвет:</label>
                         <input type="color" id="dm-color-picker" value="#e0e0e0">
                         <button type="button" onclick="applyColorTag('dm-message-content', 'dm-color-picker')">Применить цвет</button>
                    </div>
                    <button type="submit">Отправить</button>
                </form>
            </div>
            <div id="dm-no-selection-placeholder" class="no-dm-selected">Выберите диалог или найдите пользователя, чтобы начать чат.</div>

        {% else %}
            <p style="text-align:center; margin-top: 20px; font-size:0.9em;">
                <a href="{{ url_for('login', next=request.url) }}">Войдите</a>, чтобы использовать сообщения.
            </p>
        {% endif %}
    </div>

    <div class="main-forum-container" id="main-forum-container">
        <div class="main-content-wrapper" id="main-content-wrapper">
            <div class="header">
                <div style="font-size: 1em; font-weight: light;"><a href="{{ url_for('index') }}">AnonN</a></div>
                <div class="nav">
                    {% if current_user.is_authenticated %}
                        <span>Привет, <a href="{{ url_for('user_profile', username=current_user.username) }}" class="username-link">{{ current_user.username }}</a>!</span>
                         {% if current_user.is_admin %}
                            <a href="{{ url_for('admin_reports') }}">Жалобы</a> {# Link to admin reports #}
                        {% endif %}
                        <a href="{{ url_for('logout') }}">Выйти</a>
                    {% else %}
                        <a href="{{ url_for('login') }}">Войти</a>
                        <a href="{{ url_for('register') }}">Регистрация</a>
                    {% endif %}
                </div>
            </div>

            <div id="flash-container">
                {% with messages = get_flashed_messages(with_categories=true) %}
                    {% if messages %}
                        <ul class="flash-messages">
                        {% for category, message in messages %}
                            <li class="flash-{{ category }}">{{ message }}</li>
                        {% endfor %}
                        </ul>
                    {% endif %}
                {% endwith %}
            </div>

            {% if not request.endpoint in ['edit_post', 'user_profile', 'edit_profile', 'admin_reports'] and not request.endpoint.startswith('dm_') %} {# Exclude admin_reports #}
            <div class="sort-options">
                <div>
                    Сортировать по:
                    <a href="{{ url_for('index', sort_by='score_desc', tag=tag_filter or '') }}">Рейтингу (убыв.)</a> |
                    <a href="{{ url_for('index', sort_by='date_desc', tag=tag_filter or '') }}">Дате (новые)</a> |
                    <a href="{{ url_for('index', sort_by='date_asc', tag=tag_filter or '') }}">Дате (старые)</a>
                </div>
                <div>
                    <label for="tag-filter">Фильтр по тегу:</label>
                    <select id="tag-filter" class="tag-filter-dropdown" onchange="window.location.href = this.value;">
                        <option value="{{ url_for('index', sort_by=sort_by, tag='all') }}" {% if tag_filter is none or tag_filter == 'all' %}selected{% endif %}>Все теги</option>
                        {% for tag_item in all_tags %}
                            <option value="{{ url_for('index', sort_by=sort_by, tag=tag_item.name) }}" {% if tag_filter == tag_item.name %}selected{% endif %}>{{ tag_item.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                {% if tag_filter and tag_filter != 'all' %}
                <div>
                    <a href="{{ url_for('index', sort_by=sort_by, tag='') }}">Сбросить фильтр тегов</a>
                </div>
                {% endif %}
            </div>
            {% endif %}

            {{ content | safe }}
        </div> {# End of main-content-wrapper #}
    </div> {# End of main-forum-container #}

    {% if new_post_form_html_for_bottom_panel and not request.endpoint in ['edit_post', 'user_profile', 'edit_profile', 'admin_reports'] %} {# Exclude admin_reports #}
        <button id="bottom-panel-toggle" class="panel-toggle-button">&#9660;</button>
        <div class="fixed-bottom-new-post-panel" id="fixed-bottom-panel">
             <form method="POST" action="{{ url_for('index') }}" id="new-post-form">
                <textarea id="new-post-content" name="content" placeholder="Напишите что-нибудь... (форматирование: &lt;b&gt;, &lt;i&gt;, &lt;u&gt;)" required rows="3"></textarea> {# Removed font tag hint #}
                <div class="color-picker-container"> {# Added color picker for new post #}
                     <label for="post-color-picker">Цвет текста:</label>
                     <input type="color" id="post-color-picker" value="#e0e0e0">
                     <button type="button" onclick="applyColorTag('new-post-content', 'post-color-picker')">Применить цвет</button>
                </div>
                <input type="text" id="tags" name="tags" placeholder="Теги (через запятую, например: новости, обсуждение)">
                <div class="controls-container">
                    {% if current_user.is_authenticated and current_user.is_admin %}
                        <div class="pinned-checkbox-container">
                            <input type="checkbox" id="pinned" name="pinned">
                            <label for="pinned" class="checkbox-label">Закрепить</label>
                        </div>
                    {% endif %}
                    <button type="submit">Отправить</button>
                </div>
             </form>
        </div>
    {% endif %}

    <div id="reportModal" class="modal">
        <div class="modal-content">
            <span class="close-button">&times;</span>
            <h3>Пожаловаться на пользователя</h3>
            <form id="report-user-form">
                <input type="hidden" id="reported-user-id" name="reported_user_id">
                <textarea id="report-reason" name="reason" placeholder="Опишите причину жалобы..." required rows="5"></textarea>
                <button type="submit" class="button">Отправить жалобу</button>
            </form>
        </div>
    </div>


    <script>
        // Existing JS for forum posts, polling, voting etc.
        let latestKnownPostId = 0;
        let postPollingIntervalId = null;
        let isPostPollingActive = true;

        function getLatestPostIdOnPage() {
            const postsContainer = document.getElementById('posts-container');
            if (!postsContainer) return 0;
            const firstPost = postsContainer.querySelector('.post:not(:has(.pinned-indicator))');
            if (firstPost && firstPost.dataset.postId) {
                return parseInt(firstPost.dataset.postId, 10);
            }
            return 0;
        }

        function stopPostPolling() {
            if (postPollingIntervalId) {
                clearInterval(postPollingIntervalId);
                postPollingIntervalId = null;
                isPostPollingActive = false;
                console.log("Post polling stopped.");
            }
        }

        function displayFlashMessage(message, category) {
            const container = document.getElementById('flash-container');
            if (!container) return;
            const ul = document.createElement('ul');
            ul.className = 'flash-messages';
            const li = document.createElement('li');
            li.className = `flash-${category}`;
            li.innerHTML = message; // Use innerHTML to allow <br>
            ul.appendChild(li);
            container.insertBefore(ul, container.firstChild);
            setTimeout(() => { if (ul.parentNode === container) { ul.remove(); } }, 5000);
        }

        function handleFetchError(error, actionType = 'действие') {
            console.error(`${actionType} Error:`, error);
            let displayMessage = `Не удалось выполнить ${actionType}. Пожалуйста, попробуйте снова.`;
            if (error.message === 'Forbidden') displayMessage = 'Действие запрещено. Возможно, вы забанены.';
            else if (error.message === 'Unauthorized') displayMessage = `Пожалуйста, войдите, чтобы выполнить ${actionType}.`;
            else if (error.message) displayMessage = error.message;
            displayFlashMessage(displayMessage, 'error');
            if (error.message === 'Forbidden' || error.message === 'Unauthorized') {
                stopPostPolling();
                stopDmPolling();
            }
        }

        async function processResponse(response, actionType = 'действие') {
             if (!response.ok) {
                let errorMessage = `Ошибка сети: ${response.statusText}`;
                let errorType = 'NetworkError';
                if (response.status === 401) errorType = 'Unauthorized';
                if (response.status === 403) errorType = 'Forbidden';
                try {
                    const errData = await response.json();
                    errorMessage = errData.message || errorMessage;
                } catch (e) { /* Ignore if not JSON */ }
                 const error = new Error(errorMessage);
                 error.name = errorType;
                 throw error;
            }
             const contentType = response.headers.get("content-type");
             if (contentType && contentType.indexOf("application/json") !== -1) {
                 return await response.json();
             }
             return null; // Or throw an error if non-JSON is unexpected
        }

        document.addEventListener('click', function(event) {
            if (event.target.matches('.vote-button')) {
                event.preventDefault();
                const button = event.target;
                if (button.disabled) return;
                const postId = button.dataset.postId;
                const voteType = button.dataset.voteType;
                const url = `/vote/${postId}/${voteType}`;
                button.disabled = true; button.style.opacity = '0.7';
                fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' } })
                .then(response => processResponse(response, 'голосование'))
                .then(data => {
                    if (data && data.success) {
                        const scoreElement = document.getElementById(`score-${postId}`);
                        if (scoreElement) {
                            scoreElement.textContent = data.new_score;
                            scoreElement.className = 'post-score';
                            if (data.new_score > 0) scoreElement.classList.add('score-positive');
                            else if (data.new_score < 0) scoreElement.classList.add('score-negative');
                            else scoreElement.classList.add('score-neutral');
                        }
                        const likeButton = document.querySelector(`.vote-button.like-button[data-post-id='${postId}']`);
                        const dislikeButton = document.querySelector(`.vote-button.dislike-button[data-post-id='${postId}']`);
                        if (likeButton) likeButton.classList.remove('active');
                        if (dislikeButton) dislikeButton.classList.remove('active');
                        if (data.user_vote === 1 && likeButton) likeButton.classList.add('active');
                        else if (data.user_vote === -1 && dislikeButton) dislikeButton.classList.add('active');
                        if (data.flash_messages) data.flash_messages.forEach(fm => displayFlashMessage(fm.message, fm.category));
                    } else if (data) handleFetchError(new Error(data.message || 'Ошибка при голосовании.'), 'голосование');
                })
                .catch(error => handleFetchError(error, 'голосование'))
                .finally(() => {
                     const currentButton = document.querySelector(`.vote-button[data-post-id='${postId}'][data-vote-type='${voteType}']`);
                     if(currentButton){ currentButton.disabled = false; currentButton.style.opacity = '1';}
                });
            }
        });

        function initializeNewPostFormListener() {
            const newPostForm = document.getElementById('new-post-form');
            if (newPostForm) {
                newPostForm.addEventListener('submit', function(event) {
                    event.preventDefault();
                    const formData = new FormData(newPostForm);
                    const submitButton = newPostForm.querySelector('button[type="submit"]');
                    submitButton.disabled = true; submitButton.style.opacity = '0.7'; submitButton.textContent = 'Отправка...';
                    fetch(newPostForm.action, { method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                    .then(response => processResponse(response, 'отправка поста'))
                    .then(data => {
                        if (data && data.success && data.post_html && data.new_post_id) {
                            newPostForm.reset();
                            const postsContainer = document.getElementById('posts-container');
                            if (postsContainer) {
                                const placeholder = postsContainer.querySelector('.no-posts-placeholder');
                                if(placeholder) placeholder.remove();
                                postsContainer.insertAdjacentHTML('afterbegin', data.post_html);
                                const newPostElement = postsContainer.firstElementChild;
                                if (newPostElement) {
                                    newPostElement.classList.add('new-post-highlight');
                                    latestKnownPostId = Math.max(latestKnownPostId, data.new_post_id);
                                }
                            }
                            displayFlashMessage(data.message || 'Пост успешно создан!', 'success');
                            if (data.flash_messages) data.flash_messages.forEach(fm => displayFlashMessage(fm.message, fm.category));
                        } else if (data) handleFetchError(new Error(data.message || 'Не удалось создать пост.'), 'отправка поста');
                    })
                    .catch(error => handleFetchError(error, 'отправка поста'))
                    .finally(() => { submitButton.disabled = false; submitButton.style.opacity = '1'; submitButton.textContent = 'Отправить'; });
                });
            }
        }

        function fetchNewPosts() {
            if (!isPostPollingActive || document.hidden || !document.getElementById('posts-container')) return;
            const currentLatestId = getLatestPostIdOnPage();
            latestKnownPostId = Math.max(latestKnownPostId, currentLatestId);
            const url = `/get_new_posts/${latestKnownPostId}`;
            fetch(url)
                .then(response => processResponse(response, 'проверка новых постов'))
                .then(data => {
                    if (data && data.success && data.posts_html && data.posts_html.length > 0) {
                        const postsContainer = document.getElementById('posts-container');
                        if (postsContainer) {
                            const placeholder = postsContainer.querySelector('.no-posts-placeholder');
                            if(placeholder) placeholder.remove();
                            let maxNewId = latestKnownPostId;
                            data.posts_html.forEach(postData => {
                                const existingPostElement = document.getElementById(`post-${postData.id}`);
                                if (existingPostElement) existingPostElement.outerHTML = postData.html;
                                else {
                                    postsContainer.insertAdjacentHTML('afterbegin', postData.html);
                                    const newPostElement = postsContainer.firstElementChild;
                                    if (newPostElement && newPostElement.id === `post-${postData.id}`) newPostElement.classList.add('new-post-highlight');
                                }
                                maxNewId = Math.max(maxNewId, postData.id);
                            });
                            latestKnownPostId = maxNewId;
                        }
                    }
                    if (data && data.flash_messages) data.flash_messages.forEach(fm => displayFlashMessage(fm.message, fm.category));
                })
                .catch(error => {
                     if (error.name === 'Forbidden' || error.name === 'Unauthorized') handleFetchError(error, 'проверка новых постов');
                     else console.warn('Post Polling Error:', error.message || error);
                });
        }

        // --- Direct Messaging JavaScript ---
        const dmUserSearchInput = document.getElementById('dm-user-search');
        const dmUserSearchResultsUl = document.getElementById('dm-user-search-results');
        const dmConversationListUl = document.getElementById('dm-conversation-list');
        const dmChatAreaContainer = document.getElementById('dm-chat-area-container');
        const dmConversationListContainer = document.getElementById('dm-conversation-list-container');
        const dmChatHeaderUsername = document.getElementById('dm-chat-with-username');
        const dmMessagesDisplayDiv = document.getElementById('dm-messages-display');
        const dmMessageForm = document.getElementById('dm-message-form');
        const dmReceiverIdInput = document.getElementById('dm-receiver-id');
        const dmMessageContentTextarea = document.getElementById('dm-message-content');
        const dmNoSelectionPlaceholder = document.getElementById('dm-no-selection-placeholder');
        const dmBackButton = document.getElementById('dm-back-to-conversations');

        let activeConversationUserId = null;
        let dmPollingIntervalId = null;
        let isDmPollingActive = false;
        let lastDmTimestamp = null;


        function showChatArea(show = true) {
            if(!dmChatAreaContainer || !dmConversationListContainer || !dmUserSearchResultsUl || !dmNoSelectionPlaceholder) return;
            if (show) {
                dmChatAreaContainer.style.display = 'flex';
                dmConversationListContainer.style.display = 'none';
                dmUserSearchResultsUl.style.display = 'none';
                dmNoSelectionPlaceholder.style.display = 'none';
            } else {
                dmChatAreaContainer.style.display = 'none';
                dmConversationListContainer.style.display = 'block';
                dmUserSearchResultsUl.style.display = 'block';
                if (dmConversationListUl.children.length === 0 && dmUserSearchResultsUl.children.length === 0) {
                     dmNoSelectionPlaceholder.style.display = 'flex'; // Use flex to center
                } else {
                     dmNoSelectionPlaceholder.style.display = 'none';
                }
            }
        }

        if(dmBackButton) {
            dmBackButton.addEventListener('click', () => {
                activeConversationUserId = null;
                stopDmPolling();
                showChatArea(false);
                loadConversations();
            });
        }

        async function loadConversations() {
            if (!current_user.is_authenticated || !dmConversationListUl) return;
            try {
                const response = await fetch('/api/direct_messages/conversations');
                const data = await processResponse(response, 'загрузка диалогов');
                if (data && data.success) {
                    dmConversationListUl.innerHTML = '';
                    if (dmNoSelectionPlaceholder && data.conversations.length === 0 && (!dmUserSearchResultsUl || dmUserSearchResultsUl.children.length === 0) ) {
                         dmNoSelectionPlaceholder.style.display = 'flex'; // Use flex to center
                    } else if (dmNoSelectionPlaceholder) {
                         dmNoSelectionPlaceholder.style.display = 'none';
                    }
                    data.conversations.forEach(convo => {
                        const li = document.createElement('li');
                        const usernameSpan = document.createElement('span');
                        usernameSpan.textContent = convo.username;
                        li.appendChild(usernameSpan);

                        li.dataset.userId = convo.user_id;
                        if (convo.unread_count > 0) {
                            const unreadSpan = document.createElement('span');
                            unreadSpan.className = 'unread-indicator';
                            unreadSpan.title = `${convo.unread_count} непрочитанных`;
                            li.appendChild(unreadSpan);
                        }
                        if (convo.user_id === activeConversationUserId) {
                            li.classList.add('active-conversation');
                        }
                        li.addEventListener('click', () => {
                            setActiveConversation(convo.user_id, convo.username);
                        });
                        dmConversationListUl.appendChild(li);
                    });
                }
            } catch (error) {
                handleFetchError(error, 'загрузка диалогов');
            }
        }

        async function setActiveConversation(userId, username) {
            if(!dmChatHeaderUsername || !dmReceiverIdInput || !dmMessagesDisplayDiv) return;

            activeConversationUserId = userId;
            dmChatHeaderUsername.textContent = username;
            dmReceiverIdInput.value = userId;
            dmMessagesDisplayDiv.innerHTML = '';
            lastDmTimestamp = null;

            document.querySelectorAll('#dm-conversation-list li').forEach(li => {
                li.classList.remove('active-conversation');
                if (parseInt(li.dataset.userId) === userId) {
                    li.classList.add('active-conversation');
                }
            });

            showChatArea(true);
            await loadMessagesForConversation(userId);
            await markMessagesAsRead(userId);
            startDmPolling();
        }

        async function loadMessagesForConversation(userId, sinceTimestamp = null) {
            if (!activeConversationUserId || activeConversationUserId !== userId || !dmMessagesDisplayDiv) return;
            let url = `/api/direct_messages/with/${userId}`;
            if (sinceTimestamp) {
                url += `?since=${sinceTimestamp}`;
            }
            try {
                const response = await fetch(url);
                const data = await processResponse(response, 'загрузка сообщений');
                if (data && data.success) {
                    // Check if we are near the bottom before adding new messages
                    const isNearBottom = dmMessagesDisplayDiv.scrollHeight - dmMessagesDisplayDiv.scrollTop <= dmMessagesDisplayDiv.clientHeight + 50; // Add a small buffer

                    data.messages.forEach(msg => {
                        appendMessageToDisplay(msg);
                        lastDmTimestamp = msg.timestamp;
                    });

                    // Scroll to bottom only if we were near the bottom or loading initial messages
                    if (isNearBottom || !sinceTimestamp) {
                         dmMessagesDisplayDiv.scrollTop = dmMessagesDisplayDiv.scrollHeight;
                    }
                    if (data.messages.length > 0 && !sinceTimestamp) {
                         markMessagesAsRead(userId);
                    }
                }
            } catch (error) {
                handleFetchError(error, 'загрузка сообщений');
            }
        }

        async function markMessagesAsRead(senderId) {
            if (!current_user.is_authenticated || !senderId) return;
            try {
                await fetch(`/api/direct_messages/mark_read/${senderId}`, { method: 'POST' });
                if(dmConversationListUl){
                    const convoLi = dmConversationListUl.querySelector(`li[data-user-id="${senderId}"] .unread-indicator`);
                    if (convoLi) convoLi.remove();
                }
            } catch (error) {
                console.error("Error marking messages as read:", error);
            }
        }


        function appendMessageToDisplay(msg) {
            if(!dmMessagesDisplayDiv) return;
            const msgDiv = document.createElement('div');
            msgDiv.classList.add('message-bubble');
            msgDiv.classList.add(msg.sender_id === current_user.id ? 'sent' : 'received');

            const contentP = document.createElement('p');
            contentP.innerHTML = msg.content;
            msgDiv.appendChild(contentP);

            const timeSpan = document.createElement('span');
            timeSpan.className = 'msg-time';
            // Parse timestamp as UTC and format for local time
            const date = new Date(msg.timestamp + 'Z');
            timeSpan.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            msgDiv.appendChild(timeSpan);

            dmMessagesDisplayDiv.appendChild(msgDiv);
        }

        if (dmMessageForm) {
            dmMessageForm.addEventListener('submit', async function(event) {
                event.preventDefault();
                if (!current_user.is_authenticated || !dmMessageContentTextarea || !dmReceiverIdInput) return;
                const content = dmMessageContentTextarea.value.trim();
                const receiverId = dmReceiverIdInput.value;
                if (!content || !receiverId) return;

                try {
                    const response = await fetch('/api/direct_messages/send', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        body: JSON.stringify({ receiver_id: receiverId, content: content })
                    });
                    const data = await processResponse(response, 'отправка сообщения');
                    if (data && data.success && data.message) {
                        appendMessageToDisplay(data.message);
                        if(dmMessagesDisplayDiv) dmMessagesDisplayDiv.scrollTop = dmMessagesDisplayDiv.scrollHeight;
                        dmMessageContentTextarea.value = '';
                        lastDmTimestamp = data.message.timestamp;
                        loadConversations();
                    } else if (data && data.message) {
                        displayFlashMessage(data.message, 'error');
                    }
                } catch (error) {
                    handleFetchError(error, 'отправка сообщения');
                }
            });
        }

        if (dmUserSearchInput) {
            dmUserSearchInput.addEventListener('input', async function() {
                if(!dmUserSearchResultsUl) return;
                const query = this.value.trim();
                dmUserSearchResultsUl.innerHTML = '';
                if (query.length < 2) {
                    if (query.length === 0) showChatArea(false);
                    return;
                }
                try {
                    const response = await fetch(`/api/users/search_for_dm?q=${encodeURIComponent(query)}`);
                    const data = await processResponse(response, 'поиск пользователей');
                    if (data && data.success) {
                        if(dmNoSelectionPlaceholder) dmNoSelectionPlaceholder.style.display = 'none';
                        data.users.forEach(user => {
                            const li = document.createElement('li');

                            const userInfoDiv = document.createElement('div');
                            const usernameLink = document.createElement('a');
                            usernameLink.href = `/user/${user.username}`;
                            usernameLink.textContent = user.username;
                            usernameLink.target = "_blank"; // Open profile in new tab
                            userInfoDiv.appendChild(usernameLink);
                            li.appendChild(userInfoDiv);

                            const actionsDiv = document.createElement('div');
                            actionsDiv.className = 'user-search-actions';

                            const messageButton = document.createElement('button');
                            messageButton.textContent = 'Написать';
                            messageButton.className = 'button';
                            messageButton.dataset.userId = user.id;
                            messageButton.dataset.username = user.username;
                            messageButton.addEventListener('click', (e) => {
                                e.stopPropagation(); // Prevent li click event
                                setActiveConversation(user.id, user.username);
                                dmUserSearchInput.value = '';
                                dmUserSearchResultsUl.innerHTML = '';
                            });
                            actionsDiv.appendChild(messageButton);
                            li.appendChild(actionsDiv);

                            // Original click to open chat directly (can be kept or removed based on preference)
                            // li.addEventListener('click', () => {
                            //     setActiveConversation(user.id, user.username);
                            //     dmUserSearchInput.value = '';
                            //     dmUserSearchResultsUl.innerHTML = '';
                            // });
                            dmUserSearchResultsUl.appendChild(li);
                        });
                         if (dmConversationListContainer && data.users.length > 0) {
                             dmConversationListContainer.style.display = 'none';
                         } else if (dmConversationListContainer) {
                             dmConversationListContainer.style.display = 'block';
                         }

                    }
                } catch (error) {
                    handleFetchError(error, 'поиск пользователей');
                }
            });
        }

        function pollNewDms() {
            if (!isDmPollingActive || !activeConversationUserId || document.hidden) return;
            loadMessagesForConversation(activeConversationUserId, lastDmTimestamp);
        }

        function startDmPolling() {
            stopDmPolling();
            isDmPollingActive = true;
            dmPollingIntervalId = setInterval(pollNewDms, 3500);
            console.log(`DM polling started for user ${activeConversationUserId}.`);
        }

        function stopDmPolling() {
            if (dmPollingIntervalId) {
                clearInterval(dmPollingIntervalId);
                dmPollingIntervalId = null;
            }
            isDmPollingActive = false;
        }

        // --- Panel Toggling Logic ---
        const leftSidebar = document.getElementById('messaging-sidebar');
        const mainForumContainer = document.getElementById('main-forum-container');
        const leftSidebarToggle = document.getElementById('left-sidebar-toggle');
        const fixedBottomPanel = document.getElementById('fixed-bottom-panel');
        const bottomPanelToggle = document.getElementById('bottom-panel-toggle');
        const mainContentWrapper = document.getElementById('main-content-wrapper');


        function updateLeftSidebarToggleButton(isCollapsed) {
            if (!leftSidebarToggle) return;
            leftSidebarToggle.innerHTML = isCollapsed ? '&raquo;' : '&laquo;'; // Use consistent arrows
            leftSidebarToggle.classList.toggle('collapsed-state', isCollapsed);
        }

        function toggleLeftSidebar() {
            if (!leftSidebar || !mainForumContainer || !leftSidebarToggle) return;

            leftSidebar.classList.toggle('collapsed');
            mainForumContainer.classList.toggle('left-sidebar-collapsed');
            const isCollapsed = leftSidebar.classList.contains('collapsed');
            updateLeftSidebarToggleButton(isCollapsed);
            localStorage.setItem('leftSidebarCollapsed', isCollapsed.toString());

            if (fixedBottomPanel) {
                 fixedBottomPanel.classList.toggle('left-sidebar-collapsed', isCollapsed);
                 // Adjust fixed bottom panel left position based on sidebar state
                 if (isCollapsed) {
                     fixedBottomPanel.style.left = '0';
                 } else {
                     // Use the CSS variable value
                     const sidebarWidth = getComputedStyle(document.documentElement).getPropertyValue('--left-sidebar-width').trim();
                     fixedBottomPanel.style.left = sidebarWidth;
                 }
            }
        }

        function updateBottomPanelToggleButton(isCollapsed) {
             if (!bottomPanelToggle) return;
            bottomPanelToggle.innerHTML = isCollapsed ? '&#9650;' : '&#9660;'; // Use up/down arrows
            bottomPanelToggle.classList.toggle('collapsed-state', isCollapsed);
        }

        function toggleBottomPanel() {
            if (!fixedBottomPanel || !mainContentWrapper || !bottomPanelToggle) return;

            fixedBottomPanel.classList.toggle('collapsed');
            mainContentWrapper.classList.toggle('bottom-panel-collapsed');
            const isCollapsed = fixedBottomPanel.classList.contains('collapsed');
            updateBottomPanelToggleButton(isCollapsed);
            localStorage.setItem('bottomPanelCollapsed', isCollapsed.toString());
        }

        // --- Report Modal JavaScript ---
        const reportModal = document.getElementById('reportModal');
        const closeButton = reportModal ? reportModal.querySelector('.close-button') : null;
        const reportUserForm = document.getElementById('report-user-form');
        const reportedUserIdInput = document.getElementById('reported-user-id');
        const reportReasonTextarea = document.getElementById('report-reason');

        // Function to open the modal
        function openReportModal(userId) {
            if (!reportModal || !reportedUserIdInput || !reportReasonTextarea) return;
            reportedUserIdInput.value = userId;
            reportReasonTextarea.value = ''; // Clear previous reason
            reportModal.style.display = 'block';
        }

        // Function to close the modal
        function closeReportModal() {
            if (!reportModal) return;
            reportModal.style.display = 'none';
        }

        // Close the modal when the user clicks on <span> (x)
        if (closeButton) {
            closeButton.onclick = function() {
                closeReportModal();
            }
        }

        // Close the modal when the user clicks anywhere outside of the modal content
        window.onclick = function(event) {
            if (event.target == reportModal) {
                closeReportModal();
            }
        }

        // Handle report form submission (This is for the modal, the profile page uses a direct form submit now)
        if (reportUserForm) {
             reportUserForm.addEventListener('submit', async function(event) {
                event.preventDefault();
                const userId = reportedUserIdInput.value;
                const reason = reportReasonTextarea.value.trim();

                if (!userId || !reason) {
                    displayFlashMessage('Пожалуйста, укажите причину жалобы.', 'error');
                    return;
                }

                try {
                    // This fetch is for the modal form submit, which is now less likely to be used
                    // as the profile page has a direct form. Keeping it for completeness if needed elsewhere.
                    const response = await fetch(`/report_user/${userId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest' // Indicate AJAX request
                        },
                        body: JSON.stringify({ reason: reason })
                    });
                    const data = await processResponse(response, 'отправка жалобы (модаль)');
                    if (data && data.success) {
                        displayFlashMessage(data.message || 'Жалоба отправлена!', 'success');
                        closeReportModal();
                    } else if (data) {
                        handleFetchError(new Error(data.message || 'Не удалось отправить жалобу.'), 'отправка жалобы (модаль)');
                    }
                } catch (error) {
                    handleFetchError(error, 'отправка жалобы (модаль)');
                }
            });
        }


        // --- Color Tag Insertion Logic ---
        function applyColorTag(textareaId, colorPickerId) {
            const textarea = document.getElementById(textareaId);
            const colorPicker = document.getElementById(colorPickerId);
            if (!textarea || !colorPicker) return;

            const color = colorPicker.value;
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            const selectedText = textarea.value.substring(start, end);

            const tagStart = `<font color='${color}'>`;
            const tagEnd = `</font>`;

            const newText = textarea.value.substring(0, start) +
                            tagStart + selectedText + tagEnd +
                            textarea.value.substring(end);

            textarea.value = newText;

            // Restore cursor position
            const newCursorPosition = start + tagStart.length + selectedText.length;
            textarea.selectionStart = newCursorPosition;
            textarea.selectionEnd = newCursorPosition;
            textarea.focus();
        }


        // --- Initialization ---
        document.addEventListener('DOMContentLoaded', () => {
            initializeNewPostFormListener();
            if (document.getElementById('posts-container')) {
                latestKnownPostId = getLatestPostIdOnPage();
                // Only start polling if we are on the main index page
                if (window.location.pathname === '/') {
                    if (isPostPollingActive) {
                         postPollingIntervalId = setInterval(fetchNewPosts, 3000);
                         console.log("Post polling started.");
                    }
                } else {
                    stopPostPolling(); // Ensure polling is stopped on other pages
                }
            } else {
                 stopPostPolling(); // Ensure polling is stopped if posts-container is not present
            }


            if (current_user && current_user.is_authenticated) {
                loadConversations();
                if (dmChatAreaContainer) showChatArea(false);
            }

            if (leftSidebarToggle) {
                leftSidebarToggle.addEventListener('click', toggleLeftSidebar);
                const isLeftCollapsed = localStorage.getItem('leftSidebarCollapsed') === 'true';
                if (isLeftCollapsed) {
                    if(leftSidebar) leftSidebar.classList.add('collapsed');
                    if(mainForumContainer) mainForumContainer.classList.add('left-sidebar-collapsed');
                    if(fixedBottomPanel) fixedBottomPanel.classList.add('left-sidebar-collapsed');
                }
                updateLeftSidebarToggleButton(isLeftCollapsed);
                 // Set initial left position for fixed bottom panel based on initial state
                if (fixedBottomPanel) {
                    const sidebarWidth = getComputedStyle(document.documentElement).getPropertyValue('--left-sidebar-width').trim();
                    fixedBottomPanel.style.left = isLeftCollapsed ? '0' : sidebarWidth;
                }
            }

            if (bottomPanelToggle && fixedBottomPanel && mainContentWrapper) {
                // Set initial bottom panel toggle position based on sidebar state
                 const isLeftSidebarCollapsed = leftSidebar && leftSidebar.classList.contains('collapsed');
                 const initialLeftMargin = isLeftSidebarCollapsed ? 0 : parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--left-sidebar-width').trim());
                 const mainContentWidth = mainForumContainer.offsetWidth; // Use main container width
                 bottomPanelToggle.style.left = `${initialLeftMargin + mainContentWidth / 2}px`;
                 bottomPanelToggle.style.transform = `translateX(-50%) translateY(50%)`; // Initial transform

                bottomPanelToggle.addEventListener('click', toggleBottomPanel);
                const isBottomCollapsed = localStorage.getItem('bottomPanelCollapsed') === 'true';
                if (isBottomCollapsed) {
                    if(fixedBottomPanel) fixedBottomPanel.classList.add('collapsed');
                    if(mainContentWrapper) mainContentWrapper.classList.add('bottom-panel-collapsed');
                }
                updateBottomPanelToggleButton(isBottomCollapsed);
            } else if (bottomPanelToggle) {
                bottomPanelToggle.style.display = 'none'; // Hide if panel is not present
            }

            // Re-calculate bottom panel toggle position on window resize
             window.addEventListener('resize', () => {
                 if (bottomPanelToggle && mainForumContainer) {
                     const isLeftSidebarCollapsed = leftSidebar && leftSidebar.classList.contains('collapsed');
                     const currentLeftMargin = isLeftSidebarCollapsed ? 0 : parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--left-sidebar-width').trim());
                     const mainContentWidth = mainForumContainer.offsetWidth;
                     bottomPanelToggle.style.left = `${currentLeftMargin + mainContentWidth / 2}px`;
                 }
             });

        });

        window.addEventListener('beforeunload', () => {
             stopPostPolling();
             stopDmPolling();
        });

        // Pass current_user object to JS
        var current_user = {
            id: {{ current_user.id if current_user.is_authenticated else 'null' }},
            is_authenticated: {{ 'true' if current_user.is_authenticated else 'false' }},
            is_admin: {{ 'true' if current_user.is_authenticated and current_user.is_admin else 'false' }}
        };

    </script>
</body>
</html>
"""


# --- User Profile Routes ---
@app.route('/user/<username>')
# @login_required  # Removed login_required to allow public profiles, report button will be conditional
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()

    profile_html = f"""
    <div class="profile-container">
        <div class="profile-header">
            <h2>Профиль: {escape_html(user.username)}</h2>
            <div class="profile-actions">
    """
    if current_user.is_authenticated:
        if current_user.id == user.id:
            profile_html += f'<a href="{url_for('edit_profile')}" class="button">Редактировать профиль</a>'
        else: # Actions for other users
            if current_user.is_admin:
                if user.is_banned:
                    profile_html += f'<form method="POST" action="{url_for('unban_user', user_id=user.id)}" style="display:inline;"><button type="submit" class="button unban-button">Разбанить</button></form>'
                else:
                    profile_html += f'<form method="POST" action="{url_for('ban_user', user_id=user.id)}" style="display:inline;"><button type="submit" class="button ban-button">Забанить</button></form>'
            # Add "Send Message" button if not viewing own profile
            profile_html += f'<button class="button" onclick="startDmFromProfile({user.id}, \'{escape_html(user.username)}\')">Написать сообщение</button>'
            # Add Report User button/form toggle
            profile_html += f'<button class="button report-button" onclick="toggleReportForm(\'{user.id}\')">Пожаловаться</button>'


    profile_html += """
            </div>
        </div>
        <div class="profile-info">
            <h3>О себе:</h3>
    """
    if user.about_me:
        profile_html += f"<p>{escape_html(user.about_me)}</p>"
    else:
        profile_html += "<p>Пользователь пока ничего не рассказал о себе.</p>"

    profile_html += """
        </div>
        <div class="profile-achievements">
            <h3>Достижения:</h3>
    """
    if user.achievements:
        profile_html += '<div class="achievements-grid">'
        for ach in user.achievements:
            profile_html += f"""
            <div class="achievement-card">
                <div class="icon">{ach.icon_emoji}</div>
                <div class="name">{escape_html(ach.name)}</div>
                <div class="description">{escape_html(ach.description)}</div>
            </div>
            """
        profile_html += '</div>'
    else:
        profile_html += "<p>У пользователя пока нет достижений.</p>"

    profile_html += """
            </div>
    """
    # Add Report Form (initially hidden)
    if current_user.is_authenticated and current_user.id != user.id:
        profile_html += f"""
        <div id="report-form-{user.id}" class="report-form" style="display: none;">
            <h4>Пожаловаться на пользователя {escape_html(user.username)}</h4>
            <form method="POST" action="{url_for('report_user', user_id=user.id)}">
                <div class="form-group">
                    <label for="report-reason-{user.id}">Причина жалобы:</label>
                    <textarea id="report-reason-{user.id}" name="reason" rows="4"></textarea>
                </div>
                <button type="submit" class="button report-button">Отправить жалобу</button>
            </form>
        </div>
        """

    profile_html += """
        </div>
    <script>
        function startDmFromProfile(userId, username) {
            // This function needs to interact with the DM sidebar logic
            // Assuming messaging sidebar elements are always in the DOM
            if (typeof setActiveConversation === 'function') {
                // If left sidebar is collapsed, expand it first
                const sidebar = document.getElementById('messaging-sidebar');
                const toggleButton = document.getElementById('left-sidebar-toggle');
                if (sidebar && sidebar.classList.contains('collapsed') && typeof toggleLeftSidebar === 'function') {
                    toggleLeftSidebar(); // Expand it
                     // Wait a bit for sidebar to expand before trying to set active conversation
                    setTimeout(() => {
                        setActiveConversation(userId, username);
                        if (dmUserSearchInput) dmUserSearchInput.value = '';
                        if (dmUserSearchResultsUl) dmUserSearchResultsUl.innerHTML = '';
                    }, 350); // Adjust timeout if needed for animation
                } else {
                    setActiveConversation(userId, username);
                    if (dmUserSearchInput) dmUserSearchInput.value = '';
                    if (dmUserSearchResultsUl) dmUserSearchResultsUl.innerHTML = '';
                }
            } else {
                console.error('setActiveConversation function not found. DM system might not be fully loaded.');
                displayFlashMessage('Не удалось открыть чат. Попробуйте обновить страницу.', 'error');
            }
        }

        function toggleReportForm(userId) {
            const form = document.getElementById(`report-form-${userId}`);
            if (form) {
                form.style.display = form.style.display === 'none' ? 'block' : 'none';
            }
        }
    </script>
    """
    return render_template_string(BASE_HTML_TEMPLATE, content=profile_html, all_tags=Tag.query.order_by(Tag.name).all())


@app.route('/report_user/<int:user_id>', methods=['POST'])
@login_required
def report_user(user_id):
    reported_user = User.query.get_or_404(user_id)

    if current_user.id == reported_user.id:
        flash('Вы не можете пожаловаться на самого себя.', 'error')
        return redirect(url_for('user_profile', username=reported_user.username))

    reason = request.form.get('reason', '').strip()

    # Optional: Add checks for duplicate reports within a time frame
    existing_report = Report.query.filter_by(
        reporter_id=current_user.id,
        reported_user_id=reported_user.id,
        is_resolved=False # Consider unresolved reports as duplicates
    ).first()

    if existing_report:
        flash('Вы уже отправили жалобу на этого пользователя.', 'info')
        return redirect(url_for('user_profile', username=reported_user.username))

    new_report = Report(
        reporter_id=current_user.id,
        reported_user_id=reported_user.id,
        reason=reason if reason else None # Store None if reason is empty
    )
    db.session.add(new_report)
    db.session.commit()

    flash('Жалоба отправлена администратору.', 'success')
    return redirect(url_for('user_profile', username=reported_user.username))


@app.route('/admin/reports')
@login_required
def admin_reports():
    if not current_user.is_admin:
        flash('У вас нет прав доступа к этой странице.', 'error')
        return redirect(url_for('index'))

    # Fetch reports, maybe order by timestamp, unresolved first
    reports = Report.query.order_by(Report.is_resolved.asc(), Report.timestamp.desc()).all()

    reports_html = """
    <div class="reports-container">
        <h2>Жалобы пользователей</h2>
    """
    if reports:
        for report in reports:
            reporter_link = f'<a href="{url_for('user_profile', username=report.reporter.username)}">{escape_html(report.reporter.username)}</a>' if report.reporter else 'Аноним'
            reported_link = f'<a href="{url_for('user_profile', username=report.reported_user.username)}">{escape_html(report.reported_user.username)}</a>' if report.reported_user else 'Неизвестный пользователь'
            report_class = 'report-item'
            if report.is_resolved:
                report_class += ' report-resolved'

            reports_html += f"""
            <div class="{report_class}">
                <div class="report-meta">
                    От: {reporter_link} на: {reported_link} ({report.timestamp.strftime("%Y-%m-%d %H:%M")})
                </div>
                <div class="report-reason">
                    Причина: {escape_html(report.reason) if report.reason else 'Не указана'}
                </div>
                <div class="report-actions">
                    {'<form method="POST" action="' + url_for('admin_resolve_report', report_id=report.id) + '" style="display:inline;"><button type="submit" class="button">Отметить как решенную</button></form>' if not report.is_resolved else ''}
                    {'<form method="POST" action="' + url_for('ban_user', user_id=report.reported_user_id) + '" style="display:inline;"><button type="submit" class="button ban-button">Забанить пользователя</button></form>' if report.reported_user and not report.reported_user.is_banned else ''}
                    {'<form method="POST" action="' + url_for('unban_user', user_id=report.reported_user_id) + '" style="display:inline;"><button type="submit" class="button unban-button">Разбанить пользователя</button></form>' if report.reported_user and report.reported_user.is_banned else ''}
                </div>
            </div>
            """
    else:
        reports_html += "<p>Нет новых жалоб.</p>"

    reports_html += "</div>"

    return render_template_string(BASE_HTML_TEMPLATE, content=reports_html, all_tags=Tag.query.order_by(Tag.name).all())

@app.route('/admin/reports/resolve/<int:report_id>', methods=['POST'])
@login_required
def admin_resolve_report(report_id):
    if not current_user.is_admin:
        flash('У вас нет прав доступа к этой странице.', 'error')
        return redirect(url_for('index'))

    report = Report.query.get_or_404(report_id)
    report.is_resolved = True
    db.session.commit()

    flash('Жалоба отмечена как решенная.', 'success')
    return redirect(url_for('admin_reports'))


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if not current_user.is_active:
        flash('Вы забанены и не можете редактировать профиль.', 'error')
        return redirect(url_for('user_profile', username=current_user.username))

    if request.method == 'POST':
        current_user.about_me = request.form.get('about_me', '').strip()
        db.session.commit()
        flash('Профиль успешно обновлен!', 'success')
        return redirect(url_for('user_profile', username=current_user.username))

    form_html = f"""
    <div class="edit-profile-form">
        <h2>Редактировать профиль</h2>
        <form method="POST" action="{url_for('edit_profile')}">
            <div class="form-group">
                <label for="about_me">Расскажите о себе:</label>
                <textarea id="about_me" name="about_me" rows="8">{html.escape(current_user.about_me or '')}</textarea>
            </div>
            <button type="submit" class="button">Сохранить изменения</button>
            <a href="{url_for('user_profile', username=current_user.username)}" class="button">Отмена</a>
        </form>
    </div>
    """
    return render_template_string(BASE_HTML_TEMPLATE, content=form_html, all_tags=Tag.query.order_by(Tag.name).all())


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':  # For new forum post
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest': # Only allow AJAX for post submission
             flash('Неверный запрос.', 'error'); return redirect(url_for('index'))

        if not current_user.is_authenticated:
            return jsonify({'success': False, 'message': 'Вы должны войти в систему, чтобы создать пост.'}), 401
        if not current_user.is_active:
            return jsonify({'success': False, 'message': 'Вы забанены и не можете создавать посты.'}), 403

        content = request.form.get('content')
        tags_string = request.form.get('tags', '')
        pinned = request.form.get('pinned') == 'on' if current_user.is_admin else False

        if not content or not content.strip():
            return jsonify({'success': False, 'message': 'Содержание поста не может быть пустым.'}), 400

        new_post = Post(content=content, author=current_user, pinned=pinned)
        tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        for tag_name in tag_names:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag: tag = Tag(name=tag_name); db.session.add(tag)
            new_post.tags.append(tag)
        db.session.add(new_post)
        db.session.commit()
        check_and_award_achievements(current_user, event_type='new_post')

        ajax_flash_messages = [{'message': msg_text, 'category': category} for category, msg_text in
                               get_flashed_messages(with_categories=True)]
        return jsonify({
            'success': True, 'message': 'Пост успешно создан!',
            'post_html': render_post(new_post), 'new_post_id': new_post.id,
            'flash_messages': ajax_flash_messages
        })

    # --- GET request for index ---
    sort_by = request.args.get('sort_by', 'date_desc')
    tag_filter_name = request.args.get('tag')
    query = Post.query
    active_tag_filter = None

    if tag_filter_name and tag_filter_name != 'all':
        tag_obj = Tag.query.filter_by(name=tag_filter_name).first()
        if tag_obj:
            query = query.join(Post.tags).filter(Tag.id == tag_obj.id);
            active_tag_filter = tag_filter_name
        else:
            tag_filter_name = None
    elif tag_filter_name == 'all':
        tag_filter_name = None

    if sort_by == 'date_asc':
        posts = query.order_by(Post.pinned.desc(), Post.date.asc()).all()
    elif sort_by == 'score_desc':
        all_matching_posts = query.order_by(Post.pinned.desc(), Post.date.desc()).all()
        posts = sorted([p for p in all_matching_posts if p.pinned], key=lambda p: p.date, reverse=True) + \
                sorted([p for p in all_matching_posts if not p.pinned], key=lambda p: p.score, reverse=True)
    else: # date_desc is default
        posts = query.order_by(Post.pinned.desc(), Post.date.desc()).all()

    all_tags_list = Tag.query.order_by(Tag.name).all()
    posts_html_list = [render_post(post) for post in posts]

    new_post_form_content_html = ""
    if current_user.is_authenticated and current_user.is_active:
        pinned_checkbox_html = f"""
            <div class="pinned-checkbox-container">
                <input type="checkbox" id="pinned" name="pinned">
                <label for="pinned" class="checkbox-label">Закрепить</label>
            </div>
        """ if current_user.is_admin else ""

        # Combined input area for bottom panel
        new_post_form_content_html = f"""
         <form method="POST" action="{url_for('index')}" id="new-post-form">
            <textarea id="new-post-content" name="content" placeholder="Напишите что-нибудь... (форматирование: &lt;b&gt;, &lt;i&gt;, &lt;u&gt;)" required rows="3"></textarea> 
            <div class="color-picker-container">
                 <label for="post-color-picker">Цвет текста:</label>
                 <input type="color" id="post-color-picker" value="#e0e0e0">
                 <button type="button" onclick="applyColorTag('new-post-content', 'post-color-picker')">Применить цвет</button>
            </div>
            <input type="text" id="tags" name="tags" placeholder="Теги (через запятую, например: новости, обсуждение)">
            <div class="controls-container">
                {pinned_checkbox_html}
                <button type="submit">Отправить</button>
            </div>
         </form>"""
    elif current_user.is_authenticated and not current_user.is_active:
        new_post_form_content_html = '<p>Вы забанены и не можете создавать посты.</p>'
    else:
        new_post_form_content_html = f'<p><a href="{url_for('login')}">Войдите</a> или <a href="{url_for('register')}">зарегистрируйтесь</a>, чтобы оставлять сообщения.</p>'

    no_posts_placeholder = '<p class="no-posts-placeholder" style="text-align:center; padding: 20px 0;">Пока нет постов. Создайте первый!</p>' if not posts else ''
    page_content = f'''
        <h2>Посты ({Post.query.count()})</h2>
        <div id="posts-container"> {''.join(posts_html_list) if posts else no_posts_placeholder} </div>'''

    return render_template_string(
        BASE_HTML_TEMPLATE, content=page_content, all_tags=all_tags_list,
        sort_by=sort_by, tag_filter=active_tag_filter,
        new_post_form_html_for_bottom_panel=new_post_form_content_html
    )


# --- Direct Messaging API Routes ---
@app.route('/api/users/search_for_dm', methods=['GET'])
@login_required
def search_users_for_dm():
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'success': False, 'users': [], 'message': 'Слишком короткий запрос для поиска.'})

    users = User.query.filter(
        User.username.ilike(f'%{query}%'),
        User.id != current_user.id,
        User.is_banned == False
    ).limit(10).all()
    # The JS part will be updated to show profile link and message button
    return jsonify({'success': True, 'users': [{'id': u.id, 'username': u.username} for u in users]})


@app.route('/api/direct_messages/conversations', methods=['GET'])
@login_required
def get_conversations():
    sent_to_ids = db.session.query(DirectMessage.receiver_id).filter(
        DirectMessage.sender_id == current_user.id).distinct()
    received_from_ids = db.session.query(DirectMessage.sender_id).filter(
        DirectMessage.receiver_id == current_user.id).distinct()

    user_ids = {uid[0] for uid in sent_to_ids}.union({uid[0] for uid in received_from_ids})

    conversations = []
    if user_ids:
        users = User.query.filter(User.id.in_(user_ids)).all()
        for user_obj in users:
            unread_count = DirectMessage.query.filter(
                DirectMessage.sender_id == user_obj.id,
                DirectMessage.receiver_id == current_user.id,
                DirectMessage.is_read == False
            ).count()

            last_msg = DirectMessage.query.filter(
                or_(
                    (DirectMessage.sender_id == current_user.id) & (DirectMessage.receiver_id == user_obj.id),
                    (DirectMessage.sender_id == user_obj.id) & (DirectMessage.receiver_id == current_user.id)
                )
            ).order_by(DirectMessage.timestamp.desc()).first()

            conversations.append({
                'user_id': user_obj.id,
                'username': user_obj.username,
                'unread_count': unread_count,
                'last_message_time': last_msg.timestamp if last_msg else datetime.min
            })
    conversations.sort(key=lambda c: c['last_message_time'], reverse=True)
    return jsonify({'success': True, 'conversations': conversations})


@app.route('/api/direct_messages/with/<int:other_user_id>', methods=['GET'])
@login_required
def get_messages_with_user(other_user_id):
    other_user = User.query.get_or_404(other_user_id)
    since_timestamp_str = request.args.get('since')

    query = DirectMessage.query.filter(
        or_(
            (DirectMessage.sender_id == current_user.id) & (DirectMessage.receiver_id == other_user_id),
            (DirectMessage.sender_id == other_user_id) & (DirectMessage.receiver_id == current_user.id)
        )
    )
    if since_timestamp_str:
        try:
            # Parse timestamp assuming it's UTC (isoformat ends with Z)
            since_timestamp = datetime.fromisoformat(since_timestamp_str.replace('Z', '+00:00'))
            query = query.filter(DirectMessage.timestamp > since_timestamp)
        except ValueError:
            return jsonify({'success': False, 'message': 'Неверный формат времени.'}), 400

    messages = query.order_by(DirectMessage.timestamp.asc()).all()

    return jsonify({'success': True, 'messages': [
        {'id': m.id, 'sender_id': m.sender_id, 'receiver_id': m.receiver_id,
         'content': escape_html(m.content),  # Already escaped here
         'timestamp': m.timestamp.isoformat(), 'is_read': m.is_read}
        for m in messages
    ]})


@app.route('/api/direct_messages/send', methods=['POST'])
@login_required
def send_direct_message():
    if not current_user.is_active:
        return jsonify({'success': False, 'message': 'Вы забанены и не можете отправлять сообщения.'}), 403

    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = data.get('content', '').strip()

    if not receiver_id or not content:
        return jsonify({'success': False, 'message': 'Получатель и содержание не могут быть пустыми.'}), 400

    receiver = User.query.get(receiver_id)
    if not receiver or receiver.is_banned:
        return jsonify({'success': False, 'message': 'Получатель не найден или забанен.'}), 404
    if receiver.id == current_user.id:
        return jsonify({'success': False, 'message': 'Нельзя отправить сообщение самому себе.'}), 400

    dm = DirectMessage(sender_id=current_user.id, receiver_id=receiver_id, content=content)
    db.session.add(dm)
    db.session.commit()

    return jsonify({'success': True, 'message': {
        'id': dm.id, 'sender_id': dm.sender_id, 'receiver_id': dm.receiver_id,
        'content': escape_html(dm.content), 'timestamp': dm.timestamp.isoformat(), 'is_read': dm.is_read
    }, 'flash_message': 'Сообщение отправлено!'})


@app.route('/api/direct_messages/mark_read/<int:sender_id>', methods=['POST'])
@login_required
def mark_dm_as_read(sender_id):
    messages_to_mark = DirectMessage.query.filter_by(
        sender_id=sender_id,
        receiver_id=current_user.id,
        is_read=False
    ).all()

    for msg in messages_to_mark:
        msg.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'marked_count': len(messages_to_mark)})


@app.route('/edit_post/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    post = Post.query.get_or_404(post_id)
    if not (current_user.is_admin or post.user_id == current_user.id):
        flash('У вас нет прав на редактирование этого поста.', 'error');
        return redirect(url_for('index'))
    if not current_user.is_active:
        flash('Вы забанены и не можете редактировать посты.', 'error');
        return redirect(url_for('index'))

    if request.method == 'POST':
        new_content = request.form.get('content')
        new_tags_string = request.form.get('tags', '')
        if not new_content or not new_content.strip():
            flash('Содержание поста не может быть пустым.', 'error')
            current_tags_str = ', '.join([tag.name for tag in post.tags])
            content_for_textarea = post.content if not new_content.strip() else new_content
            edit_form_html = f'''<h2>Редактировать пост</h2><form method="POST" action="{url_for('edit_post', post_id=post.id)}"><div class="form-group"><label for="edit-post-content">Содержание:</label><textarea id="edit-post-content" name="content" required rows="5">{html.escape(content_for_textarea)}</textarea></div><div class="form-group"><label for="edit-tags">Теги:</label><input type="text" id="edit-tags" name="tags" value="{html.escape(new_tags_string if new_tags_string else current_tags_str)}"></div><button type="submit">Сохранить</button><a href="{url_for('index', _anchor=f'post-{post.id}')}" class="button">Отмена</a></form>'''
            return render_template_string(BASE_HTML_TEMPLATE, content=edit_form_html,
                                          all_tags=Tag.query.order_by(Tag.name).all())

        original_tag_ids = {tag.id for tag in post.tags}
        post.content = new_content
        post.last_edited_at = datetime.utcnow()
        post.edit_count += 1
        post.tags.clear()
        tag_names = [tn.strip() for tn in new_tags_string.split(',') if tn.strip()]
        for tag_name in tag_names:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag: tag = Tag(name=tag_name); db.session.add(tag)
            post.tags.append(tag)
        db.session.commit()
        current_tag_ids = {tag.id for tag in post.tags}
        tag_ids_potentially_orphaned = original_tag_ids - current_tag_ids
        if tag_ids_potentially_orphaned:
            orphaned_tags = Tag.query.filter(Tag.id.in_(tag_ids_potentially_orphaned)).all()
            for tag_to_check in orphaned_tags:
                if tag_to_check and not tag_to_check.posts.count(): db.session.delete(tag_to_check) # Added check for tag existence
            db.session.commit()
        flash('Пост успешно обновлен!', 'success');
        return redirect(url_for('index', _anchor=f'post-{post.id}'))

    current_tags_str = ', '.join([tag.name for tag in post.tags])
    edit_form_html = f'''<h2>Редактировать пост</h2><form method="POST" action="{url_for('edit_post', post_id=post.id)}"><div class="form-group"><label for="edit-post-content">Содержание:</label><textarea id="edit-post-content" name="content" required rows="5">{html.escape(post.content)}</textarea></div><div class="form-group"><label for="edit-tags">Теги:</label><input type="text" id="edit-tags" name="tags" value="{html.escape(current_tags_str)}"></div><button type="submit">Сохранить</button><a href="{url_for('index', _anchor=f'post-{post.id}')}" class="button">Отмена</a></form>'''
    return render_template_string(BASE_HTML_TEMPLATE, content=edit_form_html,
                                  all_tags=Tag.query.order_by(Tag.name).all())


@app.route('/get_new_posts/<int:latest_post_id>')
def get_new_posts(latest_post_id):
    # Fetch pinned posts separately to ensure they are always at the top
    pinned_posts = Post.query.filter_by(pinned=True).order_by(Post.date.desc()).all()
    # Fetch new non-pinned posts
    new_posts_query = Post.query.filter(Post.id > latest_post_id, Post.pinned == False).order_by(Post.id.asc())
    new_posts = new_posts_query.all()

    all_posts_to_render = pinned_posts + new_posts # Combine, pinned first

    if not all_posts_to_render: return jsonify({'success': True, 'posts_html': [], 'flash_messages': []})

    posts_data = [{'id': post.id, 'html': render_post(post)} for post in all_posts_to_render]

    return jsonify(
        {'success': True, 'posts_html': posts_data, 'flash_messages': []})


@app.route('/vote/<int:post_id>/<string:vote_type_str>', methods=['POST'])
@login_required
def vote(post_id, vote_type_str):
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest': return jsonify(
        {'success': False, 'message': 'Неверный запрос.'}), 400
    if not current_user.is_active: return jsonify(
        {'success': False, 'message': 'Вы забанены и не можете голосовать.'}), 403
    post = Post.query.get_or_404(post_id)
    vote_value = 1 if vote_type_str == 'like' else -1 if vote_type_str == 'dislike' else 0
    if vote_value == 0: return jsonify({'success': False, 'message': 'Неверный тип голоса.'}), 400

    existing_vote = Vote.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    new_vote_status = None;
    standard_vote_message = ''
    if existing_vote:
        if existing_vote.vote_type == vote_value:
            db.session.delete(existing_vote);
            standard_vote_message = 'Голос убран.'
        else:
            existing_vote.vote_type = vote_value;
            existing_vote.date = datetime.utcnow();
            standard_vote_message = 'Голос изменен.';
            new_vote_status = vote_value
    else:
        new_vote = Vote(user_id=current_user.id, post_id=post_id, vote_type=vote_value);
        db.session.add(new_vote);
        standard_vote_message = 'Голос засчитан.';
        new_vote_status = vote_value
    try:
        db.session.commit()
        check_and_award_achievements(current_user, event_type='new_vote')
        if post.author: check_and_award_achievements(post.author, event_type='vote_on_my_post',
                                                     event_context={'post_id': post.id, 'post_user_id': post.user_id,
                                                                    'post_author_id': post.author.id})
        ajax_flash_messages = [{'message': msg_text, 'category': cat} for cat, msg_text in
                               get_flashed_messages(with_categories=True)]
        return jsonify(
            {'success': True, 'message': standard_vote_message, 'new_score': post.score, 'user_vote': new_vote_status,
             'flash_messages': ajax_flash_messages})
    except Exception as e:
        db.session.rollback();
        app.logger.error(f"Error voting: {e}");
        return jsonify({'success': False, 'message': 'Ошибка БД при голосовании.'}), 500


@app.route('/reply/<int:post_id>', methods=['POST'])
@login_required
def reply(post_id):
    if not current_user.is_active: flash('Вы забанены.', 'error'); return redirect(
        url_for('index', _anchor=f'post-{post_id}'))
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    if content and content.strip():
        db.session.add(Reply(content=content, post_id=post_id, author=current_user));
        db.session.commit();
        flash('Ответ добавлен!', 'success')
    else:
        flash('Содержание ответа не может быть пустым.', 'error')
    return redirect(url_for('index', _anchor=f'post-{post_id}'))


@app.route('/delete_post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if not (current_user.is_admin or post.user_id == current_user.id): flash('Нет прав.', 'error'); return redirect(
        url_for('index'))
    tag_ids_to_check = [tag.id for tag in post.tags];
    author_of_deleted_post = post.author
    db.session.delete(post);
    db.session.commit()
    if tag_ids_to_check:
        for tag_id in tag_ids_to_check:
            tag = Tag.query.get(tag_id)
            if tag and not tag.posts.count(): db.session.delete(tag)
        db.session.commit()
    if author_of_deleted_post:
        check_and_award_achievements(author_of_deleted_post, event_type='post_deleted_recheck_posts_made')
        check_and_award_achievements(author_of_deleted_post, event_type='post_deleted_recheck_total_upvotes')
    flash('Пост удален!', 'success');
    return redirect(url_for('index'))


@app.route('/delete_reply/<int:reply_id>', methods=['POST'])
@login_required
def delete_reply(reply_id):
    reply = Reply.query.get_or_404(reply_id)
    post_id = reply.post_id
    if not (current_user.is_admin or reply.user_id == current_user.id): flash('Нет прав.', 'error'); return redirect(
        url_for('index', _anchor=f'post-{post_id}'))
    db.session.delete(reply);
    db.session.commit();
    flash('Ответ удален!', 'success')
    return redirect(url_for('index', _anchor=f'post-{post_id}'))


@app.route('/ban_user/<int:user_id>', methods=['POST'])
@login_required
def ban_user(user_id):
    if not current_user.is_admin: flash('Нет прав.', 'error'); return redirect(request.referrer or url_for('index'))
    user_to_ban = User.query.get_or_404(user_id)
    if user_to_ban.id == current_user.id: flash('Нельзя забанить себя.', 'error'); return redirect(
        request.referrer or url_for('user_profile', username=user_to_ban.username))
    if user_to_ban.is_admin: flash('Нельзя забанить админа.', 'error'); return redirect(
        request.referrer or url_for('user_profile', username=user_to_ban.username))
    user_to_ban.is_banned = True;
    db.session.commit();
    flash(f'Пользователь "{escape_html(user_to_ban.username)}" забанен.', 'success')
    # Consider adding action_taken status to relevant reports
    Report.query.filter_by(reported_user_id=user_id, is_resolved=False).update({'is_resolved': True}) # Mark unresolved reports as resolved
    db.session.commit()
    return redirect(url_for('user_profile', username=user_to_ban.username))


@app.route('/unban_user/<int:user_id>', methods=['POST'])
@login_required
def unban_user(user_id):
    if not current_user.is_admin: flash('Нет прав.', 'error'); return redirect(request.referrer or url_for('index'))
    user_to_unban = User.query.get_or_404(user_id)
    user_to_unban.is_banned = False;
    db.session.commit();
    flash(f'Пользователь "{escape_html(user_to_unban.username)}" разбанен.', 'success')
    return redirect(url_for('user_profile', username=user_to_unban.username))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username');
        password = request.form.get('password');
        password_confirm = request.form.get('password_confirm')
        error = False
        if not all([username, password, password_confirm]):
            flash('Все поля обязательны.', 'error');
            error = True
        elif password != password_confirm:
            flash('Пароли не совпадают.', 'error');
            error = True
        elif len(username) < 3:
            flash('Имя пользователя < 3 символов.', 'error');
            error = True
        elif User.query.filter_by(username=username).first():
            flash(f'Имя "{escape_html(username)}" занято.', 'error');
            error = True
        if not error:
            new_user = User(username=username, about_me="");  # Initialize about_me
            new_user.set_password(password)
            if User.query.count() == 0: new_user.is_admin = True; flash('Первый пользователь - админ.', 'info')
            db.session.add(new_user);
            db.session.commit();
            flash('Регистрация успешна! Войдите.', 'success');
            return redirect(url_for('login'))
    page_content = f'''<h2>Регистрация</h2><form method="POST" action="{url_for('register')}"><div class="form-group"><label for="username">Имя:</label><input type="text" id="username" name="username" required value="{html.escape(request.form.get('username', ''))}"></div><div class="form-group"><label for="password">Пароль:</label><input type="password" id="password" name="password" required></div><div class="form-group"><label for="password_confirm">Подтвердите:</label><input type="password" id="password_confirm" name="password_confirm" required></div><button type="submit">Регистрация</button></form><p style="text-align: center;">Есть аккаунт? <a href="{url_for('login')}">Войти</a></p>'''
    return render_template_string(BASE_HTML_TEMPLATE, content=page_content, all_tags=Tag.query.order_by(Tag.name).all())


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username');
        password = request.form.get('password');
        remember = request.form.get('remember') == 'on'
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active: flash('Аккаунт забанен.', 'error'); return redirect(url_for('login'))
            login_user(user, remember=remember);
            flash('Вход выполнен!', 'success')
            next_page = request.args.get('next')
            # Ensure next_page is safe
            if next_page and next_page.startswith('/') and not next_page.startswith(
                    '//') and 'login' not in next_page and 'register' not in next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Неверное имя или пароль.', 'error')
    next_param_val = request.args.get('next')
    next_param = f"?next={next_param_val}" if next_param_val and next_param_val.startswith(
        '/') and not next_param_val.startswith('//') else ''

    page_content = f'''<h2>Вход</h2><form method="POST" action="{url_for('login')}{next_param}"><div class="form-group"><label for="username">Имя:</label><input type="text" id="username" name="username" required value="{html.escape(request.form.get('username', ''))}"></div><div class="form-group"><label for="password">Пароль:</label><input type="password" id="password" name="password" required></div><div class="form-group" style="display: flex; align-items: center;"><input type="checkbox" id="remember" name="remember" style="width: auto; margin-right: 8px;"><label for="remember" class="checkbox-label" style="margin-bottom: 0;">Запомнить</label></div><button type="submit">Войти</button></form><p style="text-align: center;">Нет аккаунта? <a href="{url_for('register')}">Регистрация</a></p>'''
    return render_template_string(BASE_HTML_TEMPLATE, content=page_content, all_tags=Tag.query.order_by(Tag.name).all())


@app.route('/logout')
@login_required
def logout():
    logout_user();
    flash('Вы вышли.', 'info');
    return redirect(url_for('index'))


def seed_achievements():
    ach_data_list = [
        {'name': "Первопроходец", 'description': "Первый пост", 'icon_emoji': "🚀", 'condition_type': "posts_made",
         'condition_value': 1},
        {'name': "Болтун", 'description': "5 постов", 'icon_emoji': "💬", 'condition_type': "posts_made",
         'condition_value': 5},
        {'name': "Оратор", 'description': "15 постов", 'icon_emoji': "🗣️", 'condition_type': "posts_made",
         'condition_value': 15},
        {'name': "Бог", 'description': "100 постов", 'icon_emoji': "GG anonchik", 'condition_type': "posts_made",
         'condition_value': 100},
        {'name': "Голосующий", 'description': "10 голосов", 'icon_emoji': "🗳️", 'condition_type': "votes_cast",
         'condition_value': 10},
        {'name': "Популярный", 'description': "Суммарно 10 лайков", 'icon_emoji': "🌟",
         'condition_type': "total_post_upvotes_received", 'condition_value': 10},
        {'name': "Мудрец", 'description': "Пост с рейтингом +5", 'icon_emoji': "💡",
         'condition_type': "post_score_reached", 'condition_value': 5},
        {'name': "GAY", 'description': "Пост с рейтингом 1", 'icon_emoji': "oOo",
         # Kept for consistency with original
         'condition_type': "post_score_reached", 'condition_value': 1},
    ]
    for ach_data in ach_data_list:
        if not Achievement.query.filter_by(name=ach_data['name']).first():
            db.session.add(Achievement(**ach_data))
    try:
        db.session.commit();
        app.logger.info("Achievements seeded.")
    except Exception as e:
        db.session.rollback();
        app.logger.error(f"Error seeding achievements: {e}")


if __name__ == '__main__':
    with app.app_context():
        print("Creating database tables...")
        db.create_all()
        print("Database tables checked/created.")
        seed_achievements()

        admin_username = os.environ.get('ADMIN_USER', 'admin')
        admin_password = os.environ.get('ADMIN_PASS', 'Play5212')  # Default password, should be changed
        if not User.query.filter_by(username=admin_username).first():
            if User.query.count() == 0:  # Create admin only if no users exist
                admin = User(username=admin_username, is_admin=True, about_me="Администратор этого форума.");
                admin.set_password(admin_password)
                db.session.add(admin);
                db.session.commit()
                print(f"Admin user '{admin_username}' created.")
            else:
                print(
                    f"Admin user '{admin_username}' not found, but other users exist. Admin not created automatically.")
        else:  # If admin user exists, ensure is_admin is true
            admin = User.query.filter_by(username=admin_username).first()
            if not admin.is_admin:
                admin.is_admin = True;
                db.session.commit();
                print(f"User '{admin_username}' set to admin.")
            else:
                print(f"Admin user '{admin_username}' exists and is admin.")

    app.run(host='0.0.0.0', port=5000, debug=True)
