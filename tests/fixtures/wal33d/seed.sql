CREATE TABLE dtc_definitions (
    code TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    description TEXT NOT NULL,
    type TEXT NOT NULL,
    locale TEXT NOT NULL DEFAULT 'en',
    is_generic BOOLEAN DEFAULT 0,
    source_file TEXT,
    PRIMARY KEY (code, manufacturer, locale)
);
INSERT INTO dtc_definitions (code, manufacturer, description, type, locale, is_generic, source_file) VALUES
 ('P0301', 'GENERIC', 'Cylinder 1 Misfire Detected', 'P', 'en', 1, 'p_codes'),
 ('P0420', 'GENERIC', 'Catalyst System Efficiency Below Threshold Bank 1', 'P', 'en', 1, 'p_codes'),
 ('P1690', 'FORD', 'Wastegate Solenoid Circuit Malfunction', 'P', 'en', 0, 'ford_codes'),
 ('P1690', 'BMW', 'Malfunction Indicator Lamp MIL Electrical', 'P', 'en', 0, 'bmw_codes'),
 ('P1741', 'GENERIC', 'Torque Converter Clutch Circuit Performance', 'P', 'en', 1, 'p_codes');
