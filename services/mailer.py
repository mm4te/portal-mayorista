# services/mailer.py
"""
Envío de mail del portal. Hoy solo existe el flujo de recuperación de
contraseña y NO hay ningún servicio de mail real conectado — ver la lista de
requisitos (variables de entorno, remitente, DNS) en el reporte del Grupo D.

Mientras tanto, el único modo soportado es loguear el link, y eso a propósito
solo detrás de app.debug o de un flag explícito: un link de reset equivale a
la contraseña en texto plano durante su ventana de vida, así que no puede
terminar en el log de producción por accidente (D1.a).
"""
import logging

from flask import current_app

from config import Config

logger = logging.getLogger(__name__)


class MailNoConfiguradoError(Exception):
    """No hay forma real de enviar el mail (ni servicio configurado ni
    fallback de log habilitado). Se deja explotar a propósito: preferimos un
    500 ruidoso en los logs a fingir que el mail salió cuando no salió nada."""


def enviar_email_reset(destinatario, link):
    if current_app.debug or Config.RESET_LOG_LINK_FALLBACK:
        logger.warning(
            "[fallback log, no hay mail service] Link de recuperación para %s: %s",
            destinatario, link
        )
        return

    raise MailNoConfiguradoError(
        "No se pudo enviar el mail de recuperación: no hay servicio de mail "
        "configurado y RESET_LOG_LINK_FALLBACK está apagado. Ver 'Para "
        "desplegar' del Grupo D para lo que hace falta configurar."
    )
