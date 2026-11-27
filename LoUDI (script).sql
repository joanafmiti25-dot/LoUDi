USE defaultdb;
SET NAMES utf8mb4;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS Sesion;
DROP TABLE IF EXISTS Bitacora_Admin;
DROP TABLE IF EXISTS Reporte;
DROP TABLE IF EXISTS Notificacion;
DROP TABLE IF EXISTS Calificacion;
DROP TABLE IF EXISTS Realiza;
DROP TABLE IF EXISTS Posee;
DROP TABLE IF EXISTS Solicita;
DROP TABLE IF EXISTS Pasajero;
DROP TABLE IF EXISTS Conductor;
DROP TABLE IF EXISTS Vehiculo;
DROP TABLE IF EXISTS Viaje;
DROP TABLE IF EXISTS Pago;
DROP TABLE IF EXISTS Estudiante;
DROP TABLE IF EXISTS Horario;
DROP TABLE IF EXISTS Administrador;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE Administrador (
    id_Administrador INT NOT NULL AUTO_INCREMENT,
    Nombre_Administrador VARCHAR(30) NOT NULL,
    Apellido_Administrador VARCHAR(20) NOT NULL,
    Correo_Administrador VARCHAR(60) NOT NULL,
    Contraseña_Administrador VARCHAR(255) NULL,
    Contraseña_Hash VARCHAR(255) NULL,
    PRIMARY KEY (id_Administrador),
    UNIQUE KEY uq_administrador_correo (Correo_Administrador)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Horario (
    idHorario INT NOT NULL AUTO_INCREMENT,
    Turno VARCHAR(15) NOT NULL,
    HoraEntrada TIME NOT NULL,
    HoraSalida TIME NOT NULL,
    PRIMARY KEY (idHorario)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Estudiante (
    NoControl INT NOT NULL,
    Nombre_Estudiante VARCHAR(30) NOT NULL,
    Apellido_Estudiante VARCHAR(30) NOT NULL,
    Correo_Estudiante VARCHAR(60) NOT NULL,
    Rol_Usuario ENUM('pasajero','conductor','ambos') NOT NULL DEFAULT 'pasajero',
    Telefono VARCHAR(15) NOT NULL,
    Cuatrimestre VARCHAR(15) NOT NULL,
    Colonia VARCHAR(20) NOT NULL,
    Municipio VARCHAR(30) NOT NULL,
    CP INT NOT NULL,
    Estado VARCHAR(50) NOT NULL,
    Calle VARCHAR(25) NOT NULL,
    NoCalle INT NOT NULL,
    `Contraseña` VARCHAR(255) NULL,
    Contraseña_Hash VARCHAR(255) NULL,
    Estado_Cuenta ENUM('activo','bloqueado') NOT NULL DEFAULT 'activo',
    Intentos_Fallidos INT NOT NULL DEFAULT 0,
    Bloqueado_Hasta DATETIME NULL,
    Reportes INT NOT NULL DEFAULT 0,
    Fecha_Registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    id_Administrador1 INT NULL,
    idHorario1 INT NULL,
    PRIMARY KEY (NoControl),
    UNIQUE KEY uq_estudiante_correo (Correo_Estudiante),
    KEY idx_estudiante_admin (id_Administrador1),
    KEY idx_estudiante_horario (idHorario1),
    CONSTRAINT fk_estudiante_admin FOREIGN KEY (id_Administrador1)
        REFERENCES Administrador(id_Administrador)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_estudiante_horario FOREIGN KEY (idHorario1)
        REFERENCES Horario(idHorario)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Pago (
    IdPago INT NOT NULL AUTO_INCREMENT,
    Monto DECIMAL(7,2) NOT NULL,
    Estatus VARCHAR(45) NOT NULL,
    Fecha DATE NOT NULL,
    PRIMARY KEY (IdPago)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Viaje (
    idViaje INT NOT NULL AUTO_INCREMENT,
    Origen VARCHAR(50) NOT NULL,
    Destino VARCHAR(50) NOT NULL,
    Precio_Estimado DECIMAL(5,2) NOT NULL,
    Asientos_Disponibles INT NOT NULL,
    Asientos_Totales INT NOT NULL,
    Estado ENUM('Publicado','Lleno','EnCurso','Finalizado','Cancelado')
        NOT NULL DEFAULT 'Publicado',
    Fecha_Hora_Salida DATETIME NULL,
    idHorario1 INT NULL,
    PRIMARY KEY (idViaje),
    KEY idx_viaje_horario (idHorario1),
    KEY idx_viaje_salida_estado (Fecha_Hora_Salida, Estado),
    CONSTRAINT chk_viaje_asientos CHECK (
        Asientos_Totales BETWEEN 1 AND 4
        AND Asientos_Disponibles BETWEEN 0 AND Asientos_Totales
    ),
    CONSTRAINT fk_viaje_horario FOREIGN KEY (idHorario1)
        REFERENCES Horario(idHorario)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Vehiculo (
    idVehiculo INT NOT NULL AUTO_INCREMENT,
    Marca VARCHAR(60) NOT NULL,
    Placa VARCHAR(10) NOT NULL,
    Modelo VARCHAR(20) NOT NULL,
    `Año` INT NOT NULL,
    Color VARCHAR(20) NOT NULL,
    NoSeguro VARCHAR(25) NOT NULL,
    Capacidad_Pasajeros INT NOT NULL,
    PRIMARY KEY (idVehiculo),
    UNIQUE KEY uq_vehiculo_placa (Placa),
    CONSTRAINT chk_vehiculo_capacidad CHECK (Capacidad_Pasajeros BETWEEN 1 AND 4)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Pasajero (
    IdPasajero1 INT NOT NULL,
    IdPago1 INT NULL,
    PRIMARY KEY (IdPasajero1),
    KEY idx_pasajero_pago (IdPago1),
    CONSTRAINT fk_pasajero_estudiante FOREIGN KEY (IdPasajero1)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pasajero_pago FOREIGN KEY (IdPago1)
        REFERENCES Pago(IdPago)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Conductor (
    IdConductor INT NOT NULL,
    NumLicencia VARCHAR(8) NOT NULL,
    Num_Viajes INT NOT NULL DEFAULT 0,
    PRIMARY KEY (IdConductor),
    UNIQUE KEY uq_conductor_licencia (NumLicencia),
    CONSTRAINT fk_conductor_estudiante FOREIGN KEY (IdConductor)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Solicita (
    idSolicitud INT NOT NULL AUTO_INCREMENT,
    IdPasajero1 INT NULL,
    Fecha DATE NOT NULL,
    Hora TIME NOT NULL,
    Califica DOUBLE(2,1) NOT NULL DEFAULT 0,
    IdViaje1 INT NULL,
    Lugares_Solicitados INT NOT NULL DEFAULT 1,
    Estado_Reserva ENUM('pendiente','confirmada','rechazada','cancelada')
        NOT NULL DEFAULT 'pendiente',
    PRIMARY KEY (idSolicitud),
    KEY idx_solicita_viaje_estado (IdViaje1, Estado_Reserva),
    KEY idx_solicita_pasajero_estado (IdPasajero1, Estado_Reserva),
    CONSTRAINT chk_solicita_lugares CHECK (Lugares_Solicitados BETWEEN 1 AND 4),
    CONSTRAINT fk_solicita_viaje FOREIGN KEY (IdViaje1)
        REFERENCES Viaje(idViaje)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_solicita_pasajero FOREIGN KEY (IdPasajero1)
        REFERENCES Pasajero(IdPasajero1)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Posee (
    idPosee BIGINT NOT NULL AUTO_INCREMENT,
    IdConductor1 INT NULL,
    IdVehiculo1 INT NULL,
    PRIMARY KEY (idPosee),
    KEY idx_posee_conductor (IdConductor1),
    UNIQUE KEY uq_posee_vehiculo (IdVehiculo1),
    CONSTRAINT fk_posee_conductor FOREIGN KEY (IdConductor1)
        REFERENCES Conductor(IdConductor)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_posee_vehiculo FOREIGN KEY (IdVehiculo1)
        REFERENCES Vehiculo(idVehiculo)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Realiza (
    idRealiza BIGINT NOT NULL AUTO_INCREMENT,
    IdConductor2 INT NULL,
    IdViaje2 INT NULL,
    IdVehiculo2 INT NULL,
    Fecha_Realiza DATE NOT NULL,
    Hora_Realiza TIME NOT NULL,
    PRIMARY KEY (idRealiza),
    KEY idx_realiza_conductor (IdConductor2),
    KEY idx_realiza_viaje (IdViaje2),
    KEY idx_realiza_vehiculo (IdVehiculo2),
    CONSTRAINT fk_realiza_conductor FOREIGN KEY (IdConductor2)
        REFERENCES Conductor(IdConductor)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_realiza_viaje FOREIGN KEY (IdViaje2)
        REFERENCES Viaje(idViaje)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_realiza_vehiculo FOREIGN KEY (IdVehiculo2)
        REFERENCES Vehiculo(idVehiculo)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Calificacion (
    idCalificacion INT NOT NULL AUTO_INCREMENT,
    idViaje1 INT NULL,
    NoControl_Evaluador INT NOT NULL,
    NoControl_Evaluado INT NOT NULL,
    Rol_Evaluado ENUM('conductor','pasajero') NOT NULL,
    Puntuacion DECIMAL(2,1) NOT NULL,
    Comentario VARCHAR(250) NULL,
    Fecha_Registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (idCalificacion),
    KEY idx_calificacion_viaje (idViaje1),
    KEY idx_calificacion_evaluador (NoControl_Evaluador),
    KEY idx_calificacion_evaluado (NoControl_Evaluado),
    CONSTRAINT chk_calificacion_puntuacion CHECK (Puntuacion BETWEEN 1 AND 5),
    CONSTRAINT fk_calificacion_viaje FOREIGN KEY (idViaje1)
        REFERENCES Viaje(idViaje)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_calificacion_evaluador FOREIGN KEY (NoControl_Evaluador)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_calificacion_evaluado FOREIGN KEY (NoControl_Evaluado)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Notificacion (
    idNotificacion INT NOT NULL AUTO_INCREMENT,
    NoControl_Destinatario INT NULL,
    id_Administrador_Destinatario INT NULL,
    Titulo VARCHAR(80) NOT NULL,
    Mensaje VARCHAR(255) NOT NULL,
    Leida TINYINT(1) NOT NULL DEFAULT 0,
    Fecha_Creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (idNotificacion),
    KEY idx_notificacion_estudiante (NoControl_Destinatario),
    KEY idx_notificacion_admin (id_Administrador_Destinatario),
    CONSTRAINT fk_notificacion_estudiante FOREIGN KEY (NoControl_Destinatario)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_notificacion_admin FOREIGN KEY (id_Administrador_Destinatario)
        REFERENCES Administrador(id_Administrador)
        ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Reporte (
    idReporte INT NOT NULL AUTO_INCREMENT,
    NoControl_Reportante INT NOT NULL,
    NoControl_Reportado INT NULL,
    idViaje1 INT NULL,
    Motivo VARCHAR(100) NOT NULL,
    Descripcion TEXT NOT NULL,
    Estado_Reporte ENUM('abierto','en_revision','resuelto','rechazado')
        NOT NULL DEFAULT 'abierto',
    Fecha_Reporte DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (idReporte),
    KEY idx_reporte_reportante (NoControl_Reportante),
    KEY idx_reporte_reportado (NoControl_Reportado),
    KEY idx_reporte_viaje (idViaje1),
    CONSTRAINT fk_reporte_reportante FOREIGN KEY (NoControl_Reportante)
        REFERENCES Estudiante(NoControl)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_reporte_reportado FOREIGN KEY (NoControl_Reportado)
        REFERENCES Estudiante(NoControl)
        ON DELETE SET NULL ON UPDATE SET NULL,
    CONSTRAINT fk_reporte_viaje FOREIGN KEY (idViaje1)
        REFERENCES Viaje(idViaje)
        ON DELETE SET NULL ON UPDATE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Bitacora_Admin (
    id BIGINT NOT NULL AUTO_INCREMENT,
    id_Administrador INT NOT NULL,
    NoControl_Afectado INT NOT NULL,
    Accion ENUM('bloqueo','desbloqueo') NOT NULL,
    Fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_bitacora_admin (id_Administrador),
    KEY idx_bitacora_estudiante (NoControl_Afectado),
    CONSTRAINT fk_bitacora_admin FOREIGN KEY (id_Administrador)
        REFERENCES Administrador(id_Administrador),
    CONSTRAINT fk_bitacora_estudiante FOREIGN KEY (NoControl_Afectado)
        REFERENCES Estudiante(NoControl)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE Sesion (
    idSesion BIGINT NOT NULL AUTO_INCREMENT,
    Id_Administrador INT NULL,
    NoControl INT NULL,
    Token_Hash CHAR(64) NOT NULL,
    Expira DATETIME NOT NULL,
    Revocada TINYINT(1) NOT NULL DEFAULT 0,
    Fecha_Creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (idSesion),
    UNIQUE KEY uq_sesion_token (Token_Hash),
    KEY idx_sesion_admin (Id_Administrador),
    KEY idx_sesion_estudiante (NoControl),
    KEY idx_sesion_expira (Expira, Revocada),
    CONSTRAINT chk_sesion_actor CHECK (
        (Id_Administrador IS NOT NULL AND NoControl IS NULL)
        OR (Id_Administrador IS NULL AND NoControl IS NOT NULL)
    ),
    CONSTRAINT fk_sesion_admin FOREIGN KEY (Id_Administrador)
        REFERENCES Administrador(id_Administrador) ON DELETE CASCADE,
    CONSTRAINT fk_sesion_estudiante FOREIGN KEY (NoControl)
        REFERENCES Estudiante(NoControl) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
