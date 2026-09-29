SET NAMES utf8mb4;

CREATE TABLE departamentos (
  id TINYINT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(40) NOT NULL UNIQUE,
  lat DECIMAL(9,6) NOT NULL,   -- capital departamental: punto para consultar el clima
  lon DECIMAL(9,6) NOT NULL
);

CREATE TABLE barrios (
  id INT PRIMARY KEY AUTO_INCREMENT,
  departamento_id TINYINT NOT NULL,
  nombre VARCHAR(80) NOT NULL,
  lat DECIMAL(9,6) NOT NULL,
  lon DECIMAL(9,6) NOT NULL,
  altitud_m FLOAT NULL,        -- datos de terreno: los aportan con el profesor
  dist_agua_m FLOAT NULL,      -- distancia al curso de agua más cercano
  FOREIGN KEY (departamento_id) REFERENCES departamentos(id),
  UNIQUE (departamento_id, nombre)
);

CREATE TABLE usuarios (
  id INT PRIMARY KEY AUTO_INCREMENT,
  nombre VARCHAR(80) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  rol ENUM('usuario','admin') NOT NULL DEFAULT 'usuario',
  barrio_id INT NULL,          -- "dónde vive"
  creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (barrio_id) REFERENCES barrios(id)
);

CREATE TABLE suscripciones (   -- configuración de alertas
  usuario_id INT NOT NULL,
  barrio_id INT NOT NULL,
  umbral TINYINT NOT NULL DEFAULT 50,  -- avisar si la probabilidad supera este %
  PRIMARY KEY (usuario_id, barrio_id),
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  FOREIGN KEY (barrio_id) REFERENCES barrios(id) ON DELETE CASCADE
);

CREATE TABLE historial_inundaciones (
  id INT PRIMARY KEY AUTO_INCREMENT,
  barrio_id INT NOT NULL,
  fecha DATE NOT NULL,
  descripcion VARCHAR(255),
  FOREIGN KEY (barrio_id) REFERENCES barrios(id)
);

INSERT INTO departamentos (nombre, lat, lon) VALUES
('Artigas',-30.40,-56.47),('Canelones',-34.52,-56.28),('Cerro Largo',-32.37,-54.17),
('Colonia',-34.47,-57.84),('Durazno',-33.38,-56.52),('Flores',-33.52,-56.90),
('Florida',-34.10,-56.21),('Lavalleja',-34.38,-55.24),('Maldonado',-34.90,-54.96),
('Montevideo',-34.90,-56.19),('Paysandú',-32.32,-58.08),('Río Negro',-33.13,-58.30),
('Rivera',-30.90,-55.55),('Rocha',-34.48,-54.34),('Salto',-31.38,-57.96),
('San José',-34.34,-56.71),('Soriano',-33.25,-58.03),('Tacuarembó',-31.71,-55.98),
('Treinta y Tres',-33.23,-54.38);

-- Barrios de ejemplo (Montevideo). Faltan los del resto del país: cargarlos desde un CSV oficial.
INSERT INTO barrios (departamento_id, nombre, lat, lon) VALUES
(10,'Pocitos',-34.9098,-56.1497),(10,'Cerro',-34.8720,-56.2560),(10,'Carrasco',-34.8860,-56.0510),
(10,'La Teja',-34.8580,-56.2280),(10,'Malvín',-34.8990,-56.1000),(10,'Paso de la Arena',-34.8470,-56.2900);
