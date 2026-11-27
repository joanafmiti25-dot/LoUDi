"""Migra contraseñas legadas a PBKDF2 y borra los valores en texto plano."""

import argparse

from main import get_db_connection
from services import hash_contrasena


def migrar(aplicar: bool) -> tuple[int, int]:
    conexion = get_db_connection()
    try:
        with conexion.cursor() as cursor:
            cursor.execute(
                """SELECT NoControl,Contraseña FROM Estudiante
                   WHERE Contraseña_Hash IS NULL AND Contraseña IS NOT NULL"""
            )
            estudiantes = cursor.fetchall()
            cursor.execute(
                """SELECT id_Administrador,Contraseña_Administrador
                   FROM Administrador
                   WHERE Contraseña_Hash IS NULL
                     AND Contraseña_Administrador IS NOT NULL"""
            )
            administradores = cursor.fetchall()

            if aplicar:
                for fila in estudiantes:
                    cursor.execute(
                        """UPDATE Estudiante
                           SET Contraseña_Hash=%s,Contraseña=NULL
                           WHERE NoControl=%s""",
                        (hash_contrasena(fila["Contraseña"]), fila["NoControl"]),
                    )
                for fila in administradores:
                    cursor.execute(
                        """UPDATE Administrador
                           SET Contraseña_Hash=%s,Contraseña_Administrador=NULL
                           WHERE id_Administrador=%s""",
                        (
                            hash_contrasena(fila["Contraseña_Administrador"]),
                            fila["id_Administrador"],
                        ),
                    )
                conexion.commit()
            else:
                conexion.rollback()
            return len(estudiantes), len(administradores)
    except Exception:
        conexion.rollback()
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Escribe los hashes y elimina las contraseñas legadas en claro.",
    )
    args = parser.parse_args()
    cantidad_estudiantes, cantidad_admins = migrar(args.apply)
    modo = "Migrados" if args.apply else "Pendientes (simulación)"
    print(
        f"{modo}: {cantidad_estudiantes} estudiantes y "
        f"{cantidad_admins} administradores."
    )
