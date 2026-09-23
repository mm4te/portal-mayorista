INSERT INTO configuracion (clave, valor) VALUES ('pago_transferencia_banco', 'Santander') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('pago_transferencia_cbu', '0720195620000003753868') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('pago_transferencia_alias', 'comendadeco.sa') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('pago_transferencia_titular', 'COMANDA DECO S.R.L.') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('pago_transferencia_cuit', '30-71958971-1') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('anuncio_franja_texto', 'Precios con IVA incluido · Mínimo de compra: $400.000 y 6 unidades · Envíos a todo el país, flete a cargo del comprador') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('minimo_compra_monto', '400000') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('minimo_compra_unidades', '6') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('contacto_whatsapp', '11 3208-6865') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('contacto_email', 'comendadeco@gmail.com') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('pago_efectivo_direccion', 'Paso 559, CABA') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;
INSERT INTO configuracion (clave, valor) VALUES ('contacto_horarios', 'Lunes a viernes de 10 a 17 hs') ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor;

-- SELECT clave, valor FROM configuracion ORDER BY clave;
