
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from pathlib import Path
import random
import string
import sqlite3
import os


# ==========================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ==========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "clave-local-las-delicias-de-ladys"
)


# ==========================================================
# CONFIGURACIÓN DE BASE DE DATOS
# ==========================================================

# En Render:
#   DATABASE_URL debe contener la conexión PostgreSQL.
#
# En local:
#   Si DATABASE_URL no existe, se utilizará:
#   instance/fiados.db
#
# Esto permite trabajar localmente con SQLite y en Render
# con PostgreSQL sin cambiar el código.

instance_path = Path(app.instance_path)

instance_path.mkdir(
    parents=True,
    exist_ok=True
)

sqlite_path = instance_path / "fiados.db"

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + sqlite_path.as_posix()
)


# ----------------------------------------------------------
# Compatibilidad con URLs antiguas de Render
# ----------------------------------------------------------

if DATABASE_URL.startswith("postgres://"):

    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1
    )


app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db = SQLAlchemy(app)


# ==========================================================
# CONFIGURACIÓN DEL ADMINISTRADOR
# ==========================================================

ADMIN_USUARIO = os.environ.get(
    "ADMIN_USUARIO",
    "Ladys"
)

ADMIN_PASSWORD = os.environ.get(
    "ADMIN_PASSWORD",
    "3847"
)


# ==========================================================
# MODELO: USUARIO / CLIENTE
# ==========================================================

class Usuario(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nombre = db.Column(
        db.String(100),
        nullable=False
    )

    telefono = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False,
        default=""
    )

    codigo = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    consumos = db.relationship(
        "Consumo",
        backref="usuario",
        lazy=True,
        cascade="all, delete-orphan"
    )


# ==========================================================
# MODELO: PRODUCTO
# ==========================================================

class Producto(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nombre = db.Column(
        db.String(100),
        nullable=False
    )

    precio = db.Column(
        db.Integer,
        nullable=False
    )


# ==========================================================
# MODELO: CONSUMO
# ==========================================================

class Consumo(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id"),
        nullable=False
    )

    total = db.Column(
        db.Integer,
        nullable=False
    )

    fecha = db.Column(
        db.DateTime,
        default=datetime.now,
        nullable=False
    )

    detalles = db.relationship(
        "DetalleConsumo",
        backref="consumo",
        lazy=True,
        cascade="all, delete-orphan"
    )


# ==========================================================
# MODELO: DETALLE DEL CONSUMO
# ==========================================================

class DetalleConsumo(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    consumo_id = db.Column(
        db.Integer,
        db.ForeignKey("consumo.id"),
        nullable=False
    )

    producto_id = db.Column(
        db.Integer,
        db.ForeignKey("producto.id"),
        nullable=False
    )

    cantidad = db.Column(
        db.Integer,
        nullable=False
    )

    subtotal = db.Column(
        db.Integer,
        nullable=False
    )

    producto = db.relationship(
        "Producto",
        backref="detalles"
    )


# ==========================================================
# GENERAR CÓDIGO ÚNICO DEL CLIENTE
# ==========================================================

def generar_codigo():

    while True:

        codigo = "EMP-" + "".join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=6
            )
        )

        existe = Usuario.query.filter_by(
            codigo=codigo
        ).first()

        if not existe:
            return codigo


# ==========================================================
# OBTENER USUARIO ACTUAL
# ==========================================================

def usuario_actual():

    if "usuario_id" not in session:

        return None

    usuario = db.session.get(
        Usuario,
        session["usuario_id"]
    )

    if not usuario:

        session.clear()

        return None

    return usuario


# ==========================================================
# VERIFICAR ADMIN
# ==========================================================

def admin_requerido():

    return session.get("admin") is True


# ==========================================================
# REPARAR BASE DE DATOS SQLITE
# ==========================================================

def reparar_base_datos():

    # ------------------------------------------------------
    # IMPORTANTE:
    #
    # Esta función solamente trabaja con SQLite.
    #
    # Si Render está usando PostgreSQL, no intenta abrir
    # /var/data/fiados.db ni ningún archivo SQLite.
    # ------------------------------------------------------

    if not DATABASE_URL.startswith("sqlite"):

        return

    # ------------------------------------------------------
    # Ruta de la base de datos local
    # ------------------------------------------------------

    db_path = Path(app.instance_path) / "fiados.db"

    if not db_path.exists():

        return

    # ------------------------------------------------------
    # Conectar con SQLite
    # ------------------------------------------------------

    conexion = sqlite3.connect(
        db_path
    )

    cursor = conexion.cursor()

    # ------------------------------------------------------
    # Verificar que exista la tabla consumo
    # ------------------------------------------------------

    cursor.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
        AND name='consumo'
        """
    )

    tabla_consumo = cursor.fetchone()

    if not tabla_consumo:

        conexion.close()

        return

    # ------------------------------------------------------
    # Revisar columnas de la tabla consumo
    # ------------------------------------------------------

    cursor.execute(
        "PRAGMA table_info(consumo)"
    )

    columnas = [
        fila[1]
        for fila in cursor.fetchall()
    ]

    # ------------------------------------------------------
    # Crear columna fecha si no existe
    # ------------------------------------------------------

    if "fecha" not in columnas:

        cursor.execute(
            """
            ALTER TABLE consumo
            ADD COLUMN fecha DATETIME
            """
        )

    # ------------------------------------------------------
    # Reparar fechas NULL
    # ------------------------------------------------------

    fecha_actual = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute(
        """
        UPDATE consumo
        SET fecha = ?
        WHERE fecha IS NULL
        """,
        (fecha_actual,)
    )

    conexion.commit()

    conexion.close()


# ==========================================================
# INICIO
# ==========================================================

@app.route("/")
def inicio():

    return render_template(
        "index.html"
    )


# ==========================================================
# REGISTRO DE CLIENTE
# ==========================================================

@app.route(
    "/registro",
    methods=["GET", "POST"]
)
def registro():

    if request.method == "POST":

        nombre = request.form.get(
            "nombre",
            ""
        ).strip()

        telefono = request.form.get(
            "telefono",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # --------------------------------------------------
        # Validar datos
        # --------------------------------------------------

        if not nombre:

            return "El nombre es obligatorio."

        if not telefono:

            return "El teléfono es obligatorio."

        # --------------------------------------------------
        # Verificar teléfono existente
        # --------------------------------------------------

        usuario_existente = Usuario.query.filter_by(
            telefono=telefono
        ).first()

        if usuario_existente:

            return (
                "Este número de teléfono "
                "ya está registrado."
            )

        # --------------------------------------------------
        # Crear contraseña
        # --------------------------------------------------

        nueva_contraseña = ""

        if password:

            nueva_contraseña = generate_password_hash(
                password
            )

        # --------------------------------------------------
        # Crear cliente
        # --------------------------------------------------

        nuevo_usuario = Usuario(

            nombre=nombre,

            telefono=telefono,

            password=nueva_contraseña,

            codigo=generar_codigo()
        )

        db.session.add(
            nuevo_usuario
        )

        db.session.commit()

        return redirect(
            url_for(
                "registro_exitoso",
                codigo=nuevo_usuario.codigo
            )
        )

    return render_template(
        "registro.html"
    )


# ==========================================================
# REGISTRO EXITOSO
# ==========================================================

@app.route(
    "/registro-exitoso/<codigo>"
)
def registro_exitoso(codigo):

    usuario = Usuario.query.filter_by(
        codigo=codigo
    ).first_or_404()

    return render_template(
        "registro_exitoso.html",
        usuario=usuario
    )


# ==========================================================
# LOGIN CLIENTE
# ==========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        telefono = request.form.get(
            "telefono",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        ).strip()

        codigo = request.form.get(
            "codigo",
            ""
        ).strip().upper()

        # ==================================================
        # ENTRAR CON CÓDIGO / LLAVE
        # ==================================================

        if codigo:

            usuario = Usuario.query.filter_by(
                codigo=codigo
            ).first()

            if not usuario:

                return "Código incorrecto."

            # ------------------------------------------------
            # La llave siempre permite entrar.
            # ------------------------------------------------

            session["usuario_id"] = usuario.id

            return redirect(
                url_for("panel")
            )

        # ==================================================
        # ENTRAR CON TELÉFONO Y CONTRASEÑA
        # ==================================================

        if not telefono:

            return "Debes ingresar tu teléfono."

        usuario = Usuario.query.filter_by(
            telefono=telefono
        ).first()

        if not usuario:

            return (
                "No existe una cuenta "
                "con este número."
            )

        # --------------------------------------------------
        # Verificar que tenga contraseña
        # --------------------------------------------------

        if not usuario.password:

            return (
                "Esta cuenta no tiene contraseña. "
                "Debes ingresar utilizando tu código."
            )

        # --------------------------------------------------
        # Verificar contraseña
        # --------------------------------------------------

        contraseña_correcta = False

        try:

            contraseña_correcta = check_password_hash(
                usuario.password,
                password
            )

        except (ValueError, TypeError):

            # ------------------------------------------------
            # Compatibilidad con contraseñas antiguas
            # guardadas directamente.
            # ------------------------------------------------

            if usuario.password == password:

                contraseña_correcta = True

                usuario.password = generate_password_hash(
                    password
                )

                db.session.commit()

        # --------------------------------------------------
        # Contraseña incorrecta
        # --------------------------------------------------

        if not contraseña_correcta:

            return "Contraseña incorrecta."

        # --------------------------------------------------
        # Iniciar sesión
        # --------------------------------------------------

        session["usuario_id"] = usuario.id

        return redirect(
            url_for("panel")
        )

    return render_template(
        "login.html"
    )


# ==========================================================
# PANEL DEL CLIENTE
# ==========================================================

@app.route("/panel")
def panel():

    usuario = usuario_actual()

    if not usuario:

        return redirect(
            url_for("login")
        )

    consumos = Consumo.query.filter_by(
        usuario_id=usuario.id
    ).all()

    deuda_total = sum(
        consumo.total
        for consumo in consumos
    )

    return render_template(
        "panel.html",
        usuario=usuario,
        deuda_total=deuda_total
    )


# ==========================================================
# REGISTRAR CONSUMO
# ==========================================================

@app.route(
    "/consumo",
    methods=["GET", "POST"]
)
def consumo():

    usuario = usuario_actual()

    if not usuario:

        return redirect(
            url_for("login")
        )

    productos = Producto.query.order_by(
        Producto.nombre
    ).all()

    # ======================================================
    # GUARDAR CONSUMO
    # ======================================================

    if request.method == "POST":

        total = 0

        detalles = []

        # --------------------------------------------------
        # Recorrer productos
        # --------------------------------------------------

        for producto in productos:

            try:

                cantidad = int(
                    request.form.get(
                        f"cantidad_{producto.id}",
                        0
                    )
                )

            except (ValueError, TypeError):

                cantidad = 0

            if cantidad > 0:

                subtotal = (
                    producto.precio * cantidad
                )

                total += subtotal

                detalles.append({

                    "producto_id": producto.id,

                    "cantidad": cantidad,

                    "subtotal": subtotal
                })

        # --------------------------------------------------
        # No seleccionó productos
        # --------------------------------------------------

        if not detalles:

            return (
                "Debes seleccionar "
                "al menos un producto."
            )

        # --------------------------------------------------
        # Crear consumo
        # --------------------------------------------------

        nuevo_consumo = Consumo(

            usuario_id=usuario.id,

            total=total,

            fecha=datetime.now()
        )

        db.session.add(
            nuevo_consumo
        )

        db.session.flush()

        # --------------------------------------------------
        # Guardar detalles
        # --------------------------------------------------

        for detalle in detalles:

            nuevo_detalle = DetalleConsumo(

                consumo_id=nuevo_consumo.id,

                producto_id=detalle["producto_id"],

                cantidad=detalle["cantidad"],

                subtotal=detalle["subtotal"]
            )

            db.session.add(
                nuevo_detalle
            )

        db.session.commit()

        return redirect(
            url_for("panel")
        )

    return render_template(
        "consumo.html",
        productos=productos
    )


# ==========================================================
# MIS CONSUMOS
# ==========================================================

@app.route("/mis-consumos")
def mis_consumos():

    usuario = usuario_actual()

    if not usuario:

        return redirect(
            url_for("login")
        )

    consumos = Consumo.query.filter_by(
        usuario_id=usuario.id
    ).order_by(
        Consumo.fecha.desc(),
        Consumo.id.desc()
    ).all()

    # ------------------------------------------------------
    # Reparar fechas NULL
    # ------------------------------------------------------

    fechas_reparadas = False

    for consumo_item in consumos:

        if consumo_item.fecha is None:

            consumo_item.fecha = datetime.now()

            fechas_reparadas = True

    if fechas_reparadas:

        db.session.commit()

    # ------------------------------------------------------
    # Calcular deuda
    # ------------------------------------------------------

    deuda_total = sum(
        consumo_item.total
        for consumo_item in consumos
    )

    return render_template(
        "mis_consumos.html",
        consumos=consumos,
        deuda_total=deuda_total
    )


# ==========================================================
# SEPARAR PEDIDO
# ==========================================================

@app.route("/separar")
def separar():

    usuario = usuario_actual()

    if not usuario:

        return redirect(
            url_for("login")
        )

    productos = Producto.query.order_by(
        Producto.nombre
    ).all()

    return render_template(
        "separar.html",
        usuario=usuario,
        productos=productos
    )


# ==========================================================
# LOGIN ADMINISTRADOR
# ==========================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        usuario = request.form.get(
            "usuario",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        # --------------------------------------------------
        # Verificar administrador
        # --------------------------------------------------

        if (
            usuario == ADMIN_USUARIO
            and password == ADMIN_PASSWORD
        ):

            session["admin"] = True

            return redirect(
                url_for("admin_panel")
            )

        return (
            "Usuario o contraseña "
            "incorrectos."
        )

    return render_template(
        "admin_login.html"
    )


# ==========================================================
# PANEL ADMINISTRADOR
# ==========================================================

@app.route("/admin/panel")
def admin_panel():

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    # ------------------------------------------------------
    # Clientes
    # ------------------------------------------------------

    usuarios = Usuario.query.order_by(
        Usuario.id.desc()
    ).all()

    # ------------------------------------------------------
    # Productos
    # ------------------------------------------------------

    productos = Producto.query.order_by(
        Producto.nombre
    ).all()

    # ------------------------------------------------------
    # Consumos
    # ------------------------------------------------------

    consumos = Consumo.query.order_by(
        Consumo.id.desc()
    ).all()

    # ------------------------------------------------------
    # Reparar fechas NULL
    # ------------------------------------------------------

    fechas_reparadas = False

    for consumo_item in consumos:

        if consumo_item.fecha is None:

            consumo_item.fecha = datetime.now()

            fechas_reparadas = True

    if fechas_reparadas:

        db.session.commit()

    # ------------------------------------------------------
    # Total de ventas
    # ------------------------------------------------------

    total_ventas = sum(
        consumo_item.total
        for consumo_item in consumos
    )

    # ------------------------------------------------------
    # Estadísticas
    # ------------------------------------------------------

    total_clientes = len(usuarios)

    total_productos = len(productos)

    total_consumos = len(consumos)

    return render_template(

        "admin_panel.html",

        usuarios=usuarios,

        productos=productos,

        consumos=consumos,

        total_ventas=total_ventas,

        total_clientes=total_clientes,

        total_productos=total_productos,

        total_consumos=total_consumos
    )


# ==========================================================
# VER CLIENTE
# ==========================================================

@app.route(
    "/admin/usuario/<int:usuario_id>"
)
def admin_ver_usuario(usuario_id):

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    # ------------------------------------------------------
    # Buscar cliente
    # ------------------------------------------------------

    usuario = db.session.get(
        Usuario,
        usuario_id
    )

    if not usuario:

        return (
            "Cliente no encontrado.",
            404
        )

    # ------------------------------------------------------
    # Buscar consumos
    # ------------------------------------------------------

    consumos = Consumo.query.filter_by(
        usuario_id=usuario.id
    ).order_by(
        Consumo.id.desc()
    ).all()

    # ------------------------------------------------------
    # Reparar fechas NULL
    # ------------------------------------------------------

    fechas_reparadas = False

    for consumo_item in consumos:

        if consumo_item.fecha is None:

            consumo_item.fecha = datetime.now()

            fechas_reparadas = True

    if fechas_reparadas:

        db.session.commit()

    # ------------------------------------------------------
    # Calcular deuda
    # ------------------------------------------------------

    deuda_total = sum(
        consumo_item.total
        for consumo_item in consumos
    )

    return render_template(

        "admin_cliente.html",

        usuario=usuario,

        consumos=consumos,

        deuda_total=deuda_total
    )


# ==========================================================
# ELIMINAR CONSUMO
# ==========================================================

@app.route(
    "/admin/consumo/eliminar/<int:consumo_id>",
    methods=["POST"]
)
def admin_eliminar_consumo(consumo_id):

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    # ------------------------------------------------------
    # Buscar consumo
    # ------------------------------------------------------

    consumo = db.session.get(
        Consumo,
        consumo_id
    )

    # ------------------------------------------------------
    # Si existe, eliminarlo
    # ------------------------------------------------------

    if consumo:

        db.session.delete(
            consumo
        )

        db.session.commit()

    # ------------------------------------------------------
    # Volver al panel administrativo
    # ------------------------------------------------------

    return redirect(
        url_for("admin_panel")
    )


# ==========================================================
# ELIMINAR CLIENTE
# ==========================================================

@app.route(
    "/admin/usuario/eliminar/<int:usuario_id>",
    methods=["POST"]
)
def admin_eliminar_usuario(usuario_id):

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    # ------------------------------------------------------
    # Buscar usuario
    # ------------------------------------------------------

    usuario = db.session.get(
        Usuario,
        usuario_id
    )

    # ------------------------------------------------------
    # Eliminar usuario
    # ------------------------------------------------------

    if usuario:

        db.session.delete(
            usuario
        )

        db.session.commit()

    return redirect(
        url_for("admin_panel")
    )


# ==========================================================
# AGREGAR PRODUCTO
# ==========================================================

@app.route(
    "/admin/producto/agregar",
    methods=["POST"]
)
def admin_agregar_producto():

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    nombre = request.form.get(
        "nombre",
        ""
    ).strip()

    try:

        precio = int(
            request.form["precio"]
        )

    except (ValueError, TypeError):

        return "El precio debe ser un número."

    # ------------------------------------------------------
    # Validar nombre
    # ------------------------------------------------------

    if not nombre:

        return (
            "El nombre del producto "
            "es obligatorio."
        )

    # ------------------------------------------------------
    # Validar precio
    # ------------------------------------------------------

    if precio < 0:

        return (
            "El precio no puede "
            "ser negativo."
        )

    # ------------------------------------------------------
    # Crear producto
    # ------------------------------------------------------

    nuevo_producto = Producto(

        nombre=nombre,

        precio=precio
    )

    db.session.add(
        nuevo_producto
    )

    db.session.commit()

    return redirect(
        url_for("admin_panel")
    )


# ==========================================================
# ELIMINAR PRODUCTO
# ==========================================================

@app.route(
    "/admin/producto/eliminar/<int:producto_id>",
    methods=["POST"]
)
def admin_eliminar_producto(producto_id):

    if not admin_requerido():

        return redirect(
            url_for("admin_login")
        )

    producto = db.session.get(
        Producto,
        producto_id
    )

    if producto:

        # --------------------------------------------------
        # Verificar si tiene consumos
        # --------------------------------------------------

        detalle = DetalleConsumo.query.filter_by(
            producto_id=producto.id
        ).first()

        if detalle:

            return (
                "No puedes eliminar este "
                "producto porque ya tiene "
                "consumos registrados."
            )

        db.session.delete(
            producto
        )

        db.session.commit()

    return redirect(
        url_for("admin_panel")
    )


# ==========================================================
# CERRAR SESIÓN ADMIN
# ==========================================================

@app.route("/admin/logout")
def admin_logout():

    session.pop(
        "admin",
        None
    )

    return redirect(
        url_for("admin_login")
    )


# ==========================================================
# CERRAR SESIÓN CLIENTE
# ==========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("inicio")
    )


# ==========================================================
# CREAR / REPARAR BASE DE DATOS
# ==========================================================

with app.app_context():

    # ------------------------------------------------------
    # Crear tablas
    # ------------------------------------------------------

    db.create_all()

    # ------------------------------------------------------
    # Reparar base de datos
    #
    # Solamente se ejecuta realmente para SQLite.
    # PostgreSQL de Render no se toca aquí.
    # ------------------------------------------------------

    reparar_base_datos()

    # ------------------------------------------------------
    # Productos iniciales
    # ------------------------------------------------------

    if Producto.query.count() == 0:

        productos_iniciales = [

            ("Empanada de hojaldre", 4700),

            ("Arepa con huevo perico", 5700),

            ("Empanada de pollo", 2500),

            ("Empanada de carne", 2400),

            ("Arepa mixta", 5700),

            (
                "Arepa frita rellena con carne molida",
                6500
            ),

            ("Plátano con salchichón", 3800),

            ("Sandwich de pollo", 5000),

            ("Sandwich de atún", 5000),

            (
                "Arepa con torta de molipollo",
                5200
            ),

            ("Panzerotti", 4500),

            ("Pandebonos", 3500),

            ("Rosca", 3500),

            ("Gaseosa", 1300),

            ("Jugo del Valle", 1300),

            ("Tinto grande", 1600),

            ("Tinto pequeño", 800),

            ("Pastel de pollo", 4700),

            ("Pastel de carne", 4700),

            ("Pastel de yuca", 4800),

            ("Burrito de pollo", 11000),

            ("Burrito de carne", 12000),

            ("Salchicarne", 15000),

            ("Salchipollo", 15000),

            ("Empanada de lechona", 4500)
        ]

        for nombre, precio in productos_iniciales:

            producto = Producto(

                nombre=nombre,

                precio=precio
            )

            db.session.add(
                producto
            )

        db.session.commit()


# ==========================================================
# INICIAR SERVIDOR
# ==========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )
