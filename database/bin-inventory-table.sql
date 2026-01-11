CREATE TABLE bin_inventory (
  bin_id  BIGINT NOT NULL,
  item_id BIGINT NOT NULL,
  qty     DECIMAL(12,3) NOT NULL DEFAULT 0,
  PRIMARY KEY (bin_id, item_id),
  CONSTRAINT fk_bin_inv_bin
    FOREIGN KEY (bin_id) REFERENCES bins(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE,
  CONSTRAINT fk_bin_inv_item
    FOREIGN KEY (item_id) REFERENCES items(id)
    ON UPDATE CASCADE
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_bin_inv_item ON bin_inventory(item_id);
