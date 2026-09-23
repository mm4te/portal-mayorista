-- Texto de la sección "Quiénes somos" del landing público de Comenda Mayorista.
--
-- Correr en el servidor, dentro de ~/portal-mayorista:
--     sqlite3 mayoristas.db < quienes_somos.sql
--
-- Los párrafos van separados por una línea en blanco. El template los convierte
-- en <p> al renderizar, así que no hace falta escribir HTML acá.
-- El título "¿Quiénes somos?" ya está en el template: este valor es solo el cuerpo.

INSERT INTO configuracion (clave, valor) VALUES ('quienes_somos_texto',
'Somos Comenda Deco, una marca de decoración moderna y minimalista nacida en Buenos Aires. Empezamos como un proyecto familiar — hoy somos un equipo comprometido con llevar piezas con diseño y personalidad a hogares de todo el país.

Trabajamos con una selección cuidada de productos en tendencia: puffs, bancos, mesas auxiliares, floreros, espejos, canastos y deco natural. Cada pieza que suma a nuestro catálogo pasa por un criterio claro: tiene que tener diseño, calidad y una relación de precio que tenga sentido.

Nuestro canal mayorista nació de la necesidad de trabajar con quienes comparten nuestra visión — locales, revendedores y emprendedores que quieren ofrecer productos diferentes, con identidad y con respaldo.

Creemos en las relaciones a largo plazo, en la comunicación directa y en crecer juntos.

Bienvenido a Comenda.')
ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;

-- Verificación:
--     sqlite3 mayoristas.db "SELECT valor FROM configuracion WHERE clave = 'quienes_somos_texto';"
