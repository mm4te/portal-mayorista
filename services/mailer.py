# services/mailer.py
"""
Envío de mail del portal. Hoy solo existe el flujo de recuperación de
contraseña y NO hay ningún servicio de mail real conectado — ver la lista de
requisitos (variables de entorno, remitente, DNS) en el reporte del Grupo D.

routes.auth.recuperar() llama a mail_configurado() ANTES de tocar cualquier
otra cosa: si no hay proveedor real ni fallback de desarrollo prendido, ni
siquiera se genera un token — se muestra el mensaje de "escribinos al
WhatsApp" y listo (arreglo posterior a D1: un cliente real no puede recibir
un 500 de una función que le ofrecemos en pantalla, y prender el fallback de
log en producción estaba descartado a propósito). enviar_email_reset() solo
se llama cuando mail_configurado() ya dijo que sí hay con qué, así que su
propio raise de acá abajo es ahora una red de seguridad para un caso que en
teoría no debería darse — no el camino esperado en producción.
"""
import logging

from flask import current_app

from config import Config

logger = logging.getLogger(__name__)


class MailNoConfiguradoError(Exception):
    """No hay forma real de enviar el mail (ni servicio configurado ni
    fallback de log habilitado). Se deja explotar a propósito: preferimos un
    500 ruidoso en los logs a fingir que el mail salió cuando no salió nada."""


def mail_configurado():
    """El modo se detecta por configuración, no por una constante: apenas
    haya un SMTP_HOST cargado, esto pasa a True solo. OJO — hoy no hay
    ningún código que sepa mandar por SMTP_HOST todavía (ver Config): el día
    que se cargue esa variable hay que pedir que se conecte el envío real
    acá, si no, enviar_email_reset() vuelve a explotar con
    MailNoConfiguradoError, solo que ahora sí lo haría con una cuenta real
    intentando usarlo."""
    return bool(Config.SMTP_HOST)


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
