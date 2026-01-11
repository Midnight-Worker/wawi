-- Räume
CREATE TABLE rooms (
  id    BIGINT PRIMARY KEY AUTO_INCREMENT,
  code  VARCHAR(32)  NOT NULL UNIQUE,   -- z.B. "R1", "WERKSTATT"
  name  VARCHAR(128) NOT NULL
) ENGINE=InnoDB;

-- Regale (gehören zu einem Raum)
CREATE TABLE shelves (
  id      BIGINT PRIMARY KEY AUTO_INCREMENT,
  room_id BIGINT NOT NULL,
  code    VARCHAR(32)  NOT NULL,        -- z.B. "S01"
  name    VARCHAR(128) NOT NULL,
  UNIQUE (room_id, code),
  CONSTRAINT fk_shelves_room
    FOREIGN KEY (room_id) REFERENCES rooms(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Fächer (gehören zu einem Regal)
CREATE TABLE bins (
  id       BIGINT PRIMARY KEY AUTO_INCREMENT,
  shelf_id BIGINT NOT NULL,
  code     VARCHAR(32)  NOT NULL,        -- z.B. "F12"
  name     VARCHAR(128) NOT NULL,
  UNIQUE (shelf_id, code),
  CONSTRAINT fk_bins_shelf
    FOREIGN KEY (shelf_id) REFERENCES shelves(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Boxen (liegen in einem Fach)
-- Barcode-String ist nur BoxID-Barcode wie "B000042"
CREATE TABLE boxes (
  id         BIGINT PRIMARY KEY AUTO_INCREMENT,
  bin_id     BIGINT NOT NULL,
  label      VARCHAR(128) NULL,          -- optional: "Schrauben M3"
  box_code   VARCHAR(32)  NOT NULL UNIQUE, -- z.B. "B000042"
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_boxes_bin
    FOREIGN KEY (bin_id) REFERENCES bins(id)
    ON UPDATE CASCADE
    ON DELETE RESTRICT
) ENGINE=InnoDB;

-- Items / Ware / Artikel
CREATE TABLE items (
  id   BIGINT PRIMARY KEY AUTO_INCREMENT,
  sku  VARCHAR(64) UNIQUE NULL,          -- optional interne Artikelnummer
  name VARCHAR(255) NOT NULL,
  note TEXT NULL
) ENGINE=InnoDB;

-- Bestand: welche Items liegen in welcher Box (mit Menge)
CREATE TABLE box_inventory (
  box_id  BIGINT NOT NULL,
  item_id BIGINT NOT NULL,
  qty     DECIMAL(12,3) NOT NULL DEFAULT 0, -- Stück oder auch Gewicht
  PRIMARY KEY (box_id, item_id),
  CONSTRAINT fk_inv_box
    FOREIGN KEY (box_id) REFERENCES boxes(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT fk_inv_item
    FOREIGN KEY (item_id) REFERENCES items(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- Indizes für Suche/Performance
CREATE INDEX idx_items_name      ON items(name);
CREATE INDEX idx_boxes_bin       ON boxes(bin_id);
CREATE INDEX idx_shelves_room    ON shelves(room_id);
CREATE INDEX idx_bins_shelf      ON bins(shelf_id);
CREATE INDEX idx_inv_item        ON box_inventory(item_id);

