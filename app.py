import os
import uuid

from flask import Flask, render_template, request, redirect, url_for, current_app, abort
from werkzeug.utils import secure_filename

from db import get_db, init_app, init_db


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def create_app():
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, 'recipes.db'),
        SCHEMA_PATH='schema.sql',
        UPLOAD_FOLDER=os.path.join(app.static_folder, 'images', 'uploads')
    )

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    init_app(app)

    database_path = app.config['DATABASE']
    if not os.path.exists(database_path):
        with app.app_context():
            init_db()

    register_routes(app)

    return app


def register_routes(app):
    @app.route('/')
    def index():
        db = get_db()
        rows = db.execute(
            'SELECT id, name, category, short_description AS description, image_path FROM recipes ORDER BY id'
        ).fetchall()
        recipes = [dict(row) for row in rows]
        return render_template('index.html', recipes=recipes, active_page='home')

    @app.route('/recipe/<int:recipe_id>')
    def recipe_detail(recipe_id):
        db = get_db()
        recipe_row = db.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()

        if recipe_row is None:
            return "Recipe not found", 404

        recipe = dict(recipe_row)
        ingredients = [line.strip() for line in (recipe.get('ingredients_text') or '').splitlines() if line.strip()]
        directions = [line.strip() for line in (recipe.get('directions_text') or '').splitlines() if line.strip()]

        recipe_context = {
            'id': recipe['id'],
            'name': recipe['name'],
            'category': recipe['category'],
            'long_description': recipe.get('long_description') or recipe.get('short_description'),
            'image_path': recipe.get('image_path') or 'images/about.webp',
            'image_alt': recipe.get('image_alt') or f"{recipe['name']} plated",
            'ingredients': ingredients,
            'directions': directions,
            'prep_time': recipe.get('prep_time'),
            'cook_time': recipe.get('cook_time'),
            'difficulty': recipe.get('difficulty')
        }

        return render_template('recipe_detail.html', recipe=recipe_context, active_page='recipe_detail')

    @app.route('/add-recipe', methods=['GET', 'POST'])
    def add_recipe():
        error = None
        if request.method == 'POST':
            name = request.form.get('recipe-name', '').strip()
            short_desc = request.form.get('recipe-desc', '').strip()
            category = request.form.get('recipe-category', '').strip() or 'Other'
            ingredients_text = request.form.get('ingredients', '')
            directions_text = request.form.get('directions', '')
            prep_time = request.form.get('prep-time', '').strip() or None
            cook_time = request.form.get('cook-time', '').strip() or None
            difficulty = request.form.get('difficulty', '').strip() or 'Unrated'
            image_file = request.files.get('image-upload')

            image_path = 'images/about.webp'
            image_alt = f'{name} plated'

            if image_file and image_file.filename:
                filename = secure_filename(image_file.filename)
                if not allowed_image(filename):
                    error = 'Please upload an image in PNG, JPG, JPEG, WEBP, or GIF format.'
                else:
                    name_root, ext = os.path.splitext(filename)
                    unique_name = f"{name_root}_{uuid.uuid4().hex[:8]}{ext.lower()}"
                    upload_folder = current_app.config['UPLOAD_FOLDER']
                    os.makedirs(upload_folder, exist_ok=True)
                    save_path = os.path.join(upload_folder, unique_name)
                    image_file.save(save_path)
                    image_path = '/'.join(['images', 'uploads', unique_name])
                    image_alt = name or filename

            if not (name and short_desc and ingredients_text.strip() and directions_text.strip()):
                error = 'Please complete all required fields before submitting.'
            else:
                if error is None:
                    db = get_db()
                    cursor = db.execute(
                        '''
                        INSERT INTO recipes (
                            name, category, short_description, long_description,
                            ingredients_text, directions_text, image_path, image_alt,
                            prep_time, cook_time, difficulty
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            name,
                            category,
                            short_desc,
                            short_desc,
                            ingredients_text,
                            directions_text,
                            image_path,
                            image_alt,
                            prep_time,
                            cook_time,
                            difficulty
                        )
                    )
                    db.commit()
                    new_id = cursor.lastrowid
                    return redirect(url_for('recipe_detail', recipe_id=new_id))

        return render_template('add_recipe.html', active_page='add_recipe', error=error)

    @app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
    def edit_recipe(recipe_id):
        db = get_db()
        recipe_row = db.execute('SELECT * FROM recipes WHERE id = ?', (recipe_id,)).fetchone()

        if recipe_row is None:
            abort(404)

        recipe = dict(recipe_row)
        error = None

        if request.method == 'POST':
            name = request.form.get('recipe-name', '').strip()
            short_desc = request.form.get('recipe-desc', '').strip()
            category = request.form.get('recipe-category', '').strip() or recipe.get('category') or 'Other'
            ingredients_text = request.form.get('ingredients', '')
            directions_text = request.form.get('directions', '')
            prep_time_input = request.form.get('prep-time')
            cook_time_input = request.form.get('cook-time')
            difficulty_input = request.form.get('difficulty')

            prep_time = (prep_time_input or '').strip() or None
            cook_time = (cook_time_input or '').strip() or None
            difficulty = (difficulty_input or '').strip()

            if prep_time is None:
                prep_time = recipe.get('prep_time')

            if cook_time is None:
                cook_time = recipe.get('cook_time')

            if not difficulty:
                difficulty = recipe.get('difficulty') or 'Unrated'
            image_file = request.files.get('image-upload')

            image_path = recipe.get('image_path') or 'images/about.webp'
            image_alt = recipe.get('image_alt') or f"{recipe.get('name', 'Recipe')} plated"

            if image_file and image_file.filename:
                filename = secure_filename(image_file.filename)
                if not allowed_image(filename):
                    error = 'Please upload an image in PNG, JPG, JPEG, WEBP, or GIF format.'
                else:
                    name_root, ext = os.path.splitext(filename)
                    unique_name = f"{name_root}_{uuid.uuid4().hex[:8]}{ext.lower()}"
                    upload_folder = current_app.config['UPLOAD_FOLDER']
                    os.makedirs(upload_folder, exist_ok=True)
                    save_path = os.path.join(upload_folder, unique_name)
                    image_file.save(save_path)
                    image_path = '/'.join(['images', 'uploads', unique_name])
                    image_alt = name or filename

            if not (name and short_desc and ingredients_text.strip() and directions_text.strip()) and error is None:
                error = 'Please complete all required fields before submitting.'

            if error is None:
                db.execute(
                    '''
                    UPDATE recipes
                    SET name = ?, category = ?, short_description = ?, long_description = ?,
                        ingredients_text = ?, directions_text = ?, image_path = ?, image_alt = ?,
                        prep_time = ?, cook_time = ?, difficulty = ?
                    WHERE id = ?
                    ''',
                    (
                        name,
                        category,
                        short_desc,
                        short_desc,
                        ingredients_text,
                        directions_text,
                        image_path,
                        image_alt,
                        prep_time,
                        cook_time,
                        difficulty,
                        recipe_id
                    )
                )
                db.commit()
                return redirect(url_for('recipe_detail', recipe_id=recipe_id))

            recipe.update({
                'name': name,
                'category': category,
                'short_description': short_desc,
                'long_description': short_desc,
                'ingredients_text': ingredients_text,
                'directions_text': directions_text,
                'image_path': image_path,
                'image_alt': image_alt,
                'prep_time': prep_time,
                'cook_time': cook_time,
                'difficulty': difficulty
            })

        return render_template('edit_recipe.html', recipe=recipe, error=error, active_page='edit_recipe')

    @app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
    def delete_recipe(recipe_id):
        db = get_db()
        cursor = db.execute('DELETE FROM recipes WHERE id = ?', (recipe_id,))
        db.commit()

        if cursor.rowcount == 0:
            abort(404)

        return redirect(url_for('index'))

    @app.route('/about')
    def about():
        return render_template('about.html', active_page='about')

    @app.route('/contact')
    def contact():
        return render_template('contact.html', active_page='contact')


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
