// Schema Neo4j — Phase 10 (F1–F4)
// Nguồn: docs/04-schema-knowledge-graph.md §5.
//
// 7 label: Person, Place, Event, Dynasty, Organization, Title, Year, Article
// Ràng buộc: uniqueness cho `entity_id` trên từng label.

CREATE CONSTRAINT person_entity_id IF NOT EXISTS
FOR (n:Person) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT place_entity_id IF NOT EXISTS
FOR (n:Place) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT event_entity_id IF NOT EXISTS
FOR (n:Event) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT dynasty_entity_id IF NOT EXISTS
FOR (n:Dynasty) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT organization_entity_id IF NOT EXISTS
FOR (n:Organization) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT title_entity_id IF NOT EXISTS
FOR (n:Title) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT year_entity_id IF NOT EXISTS
FOR (n:Year) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT article_entity_id IF NOT EXISTS
FOR (n:Article) REQUIRE n.entity_id IS UNIQUE;

CREATE CONSTRAINT entity_entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE;

// --- Index cho truy vấn ---
// LƯU Ý: Neo4j 5 Community **không** hỗ trợ index toàn cục (`FOR (n) ON (...)`
// → SyntaxError "Invalid input ')': expected ':'"; `FOR (n:*)` cũng không
// hỗ trợ). Chỉ index theo từng label được dùng.
// Vì vậy mọi truy vấn nạp/đọc phải MATCH **kèm label** để dùng được index;
// index dưới đây tạo theo từng label cho các property hay truy vấn:
// `name`, `name_normalized` (tìm entity), `wiki_url`, `wikidata_qid`.
CREATE INDEX person_birth_year IF NOT EXISTS
FOR (n:Person) ON (n.birth_year);

CREATE INDEX person_death_year IF NOT EXISTS
FOR (n:Person) ON (n.death_year);

CREATE INDEX person_reign_start IF NOT EXISTS
FOR (n:Person) ON (n.reign_start);

CREATE INDEX person_reign_end IF NOT EXISTS
FOR (n:Person) ON (n.reign_end);

// --- Index tìm entity theo tên (theo từng label) ---
CREATE INDEX person_name IF NOT EXISTS
FOR (n:Person) ON (n.name);

CREATE INDEX person_name_normalized IF NOT EXISTS
FOR (n:Person) ON (n.name_normalized);

CREATE INDEX place_name IF NOT EXISTS
FOR (n:Place) ON (n.name);

CREATE INDEX place_name_normalized IF NOT EXISTS
FOR (n:Place) ON (n.name_normalized);

CREATE INDEX event_name IF NOT EXISTS
FOR (n:Event) ON (n.name);

CREATE INDEX event_name_normalized IF NOT EXISTS
FOR (n:Event) ON (n.name_normalized);

CREATE INDEX dynasty_name IF NOT EXISTS
FOR (n:Dynasty) ON (n.name);

CREATE INDEX dynasty_name_normalized IF NOT EXISTS
FOR (n:Dynasty) ON (n.name_normalized);

CREATE INDEX organization_name IF NOT EXISTS
FOR (n:Organization) ON (n.name);

CREATE INDEX organization_name_normalized IF NOT EXISTS
FOR (n:Organization) ON (n.name_normalized);

CREATE INDEX title_name IF NOT EXISTS
FOR (n:Title) ON (n.name);

CREATE INDEX title_name_normalized IF NOT EXISTS
FOR (n:Title) ON (n.name_normalized);

CREATE INDEX year_name IF NOT EXISTS
FOR (n:Year) ON (n.name);

CREATE INDEX year_name_normalized IF NOT EXISTS
FOR (n:Year) ON (n.name_normalized);

CREATE INDEX article_name IF NOT EXISTS
FOR (n:Article) ON (n.name);

CREATE INDEX article_name_normalized IF NOT EXISTS
FOR (n:Article) ON (n.name_normalized);

CREATE INDEX entity_name IF NOT EXISTS
FOR (n:Entity) ON (n.name);

CREATE INDEX entity_name_normalized IF NOT EXISTS
FOR (n:Entity) ON (n.name_normalized);
