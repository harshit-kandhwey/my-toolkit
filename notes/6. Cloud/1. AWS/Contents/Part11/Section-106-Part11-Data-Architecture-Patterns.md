# Part 11, Section 8: Data Engineering Architecture Patterns — Lakehouse, ETL/ELT

## 1. Definition

**Plain language:** Sections 1 through 7 introduced seven individual services — Glue, Lake Formation, Athena, EMR, Redshift Spectrum, QuickSight, OpenSearch. This section is the synthesis: how do real organizations actually combine these into coherent, named architectural patterns, and — just as importantly for interviews — how do you reason about which pattern fits a given set of requirements, the same kind of decision-framework thinking §67 applied to messaging services and §77 applied to observability.

**Precise definition:** This section covers the two dominant data engineering architectural patterns built on top of this Part's services — the **data lakehouse** (combining data lake storage flexibility with data-warehouse-like query performance and transactional guarantees) and the **ETL versus ELT** processing-order decision — providing a structured framework for how and when to apply each, synthesizing every service covered in §99-105.

## 2. Why This Framework Exists / Problem It Solves

Across §99-105, seven services each solved a distinct piece of the data engineering puzzle: cataloging (Glue), governance (Lake Formation), interactive SQL (Athena), heavy processing (EMR), warehouse/lake bridging (Redshift Spectrum), visualization (QuickSight), and search/log analytics (OpenSearch). Engineers who don't step back and see how these compose into intentional architectural patterns tend to either under-architect (treating the data lake as an unstructured dumping ground, §99 §15's "data swamp" anti-pattern) or over-architect (building unnecessarily complex, disconnected pipelines where a simpler, well-understood pattern would have served just as well). This section exists to make the two most important composed patterns — lakehouse architecture and the ETL/ELT decision — explicit and named, rather than something each team reinvents independently.

## 3. Prerequisites and Dependencies

- All of §99-105 — this section is a synthesis, assuming fluency with every service compared here.
- **Amazon Redshift** (§55) — relevant background for the lakehouse pattern's warehouse-side half.

## 4. The Data Lakehouse Pattern

### 4.1 What Problem the Lakehouse Solves

- Traditional data lakes (§99) offer schema-flexible, cheap, at-scale storage but historically lacked the transactional guarantees (atomic multi-row updates, consistent point-in-time snapshots, reliable concurrent writes) that traditional data warehouses provide natively — meaning a data lake table could, in some architectures, be read mid-update, or updating/deleting specific rows in an S3-based table required awkward, error-prone workarounds rather than a clean SQL `UPDATE`/`DELETE`.
- Traditional data warehouses (Redshift, §55) provide those transactional guarantees natively but require loading data into proprietary, warehouse-managed storage — losing the data lake's format flexibility, its ability to be queried directly by multiple different engines (Athena, EMR, OpenSearch) without loading, and its more favorable cost profile at very large scale.
- The **lakehouse pattern** aims to get both: data lake-style storage (S3, open file formats, queryable by many engines) _plus_ warehouse-style transactional guarantees and performance, typically achieved via a **table format layer** — open-source technologies like **Apache Iceberg**, **Apache Hudi**, or **Delta Lake** — sitting on top of the raw Parquet/ORC files in S3, adding a metadata layer that tracks table versions/snapshots, enables atomic commits, and supports row-level updates/deletes directly against data lake storage.
- 🔑 **Key takeaway:** a lakehouse isn't a separate AWS service — it's an architectural pattern combining this Part's existing services (S3 storage, Glue Catalog, Athena/EMR/Redshift Spectrum as query engines) with an open table-format layer (Iceberg being the most common current choice with strong native AWS integration, including native Glue Data Catalog and Athena support) that adds warehouse-like guarantees on top of lake storage.

### 4.2 How This Maps to Part 11's Services

| Lakehouse Layer                    | AWS Service(s)                                                                                                           |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Storage                            | S3 (§39)                                                                                                                 |
| Table format (transactional layer) | Apache Iceberg (or Hudi/Delta Lake) — open-source, not itself an AWS service, but with native support in Glue and Athena |
| Catalog/metadata                   | Glue Data Catalog (§99), tracking Iceberg table metadata alongside standard table definitions                            |
| Governance                         | Lake Formation (§100), extending its column/row-level permissions to Iceberg-format tables                               |
| Query engines                      | Athena (§101), EMR/Spark (§102), Redshift Spectrum (§103) — all with native or growing Iceberg support                   |

- ⚠️ **Warning:** table-format support and specific capabilities (which engines fully support which table format, exact feature parity) evolve regularly across AWS's analytics services — verify current documentation for the specific table format and engine-version combination relevant to a given design, rather than assuming universal, unconditional support across every service.

### 4.3 Lakehouse Decision Criterion

- Choose a lakehouse architecture (an open table format layered on data lake storage) specifically when a workload needs **both** data lake benefits (open formats, multi-engine queryability, S3-scale cost profile) **and** genuine transactional requirements a plain Parquet-on-S3 table doesn't provide well — row-level updates/deletes (e.g., implementing GDPR-style "right to be forgotten" deletion against a data lake table), concurrent writers needing consistency guarantees, or reliable point-in-time table snapshots for reproducible analytics.
- If a workload is purely append-only (new partitions added, nothing ever updated/deleted) and doesn't need multiple concurrent writers with strong consistency, a plain, non-lakehouse Parquet-on-S3 table (§99's original pattern) remains simpler and entirely adequate — the lakehouse pattern's added complexity is justified specifically by the transactional requirements it solves, not adopted by default.

## 5. ETL vs. ELT — The Processing-Order Decision

### 5.1 ETL — Extract, Transform, Load

- **Extract** data from source systems, **Transform** it (clean, validate, reshape, aggregate) _before_ loading, then **Load** the already-transformed result into its destination.
- This is the pattern this Part has largely assumed so far — a Glue ETL Job or EMR job (§99, §4) transforms raw data into curated Parquet _before_ it lands in the curated zone, meaning the transformation happens on dedicated processing infrastructure, separate from wherever the data ultimately gets queried.
- Best fit: when the transformation logic is complex, needs to happen once and be reused by many downstream consumers, or when the destination system (a traditional data warehouse with limited compute, or an application expecting a specific, already-clean shape) isn't well-suited to doing heavy transformation itself.

### 5.2 ELT — Extract, Load, Transform

- **Extract** data from source systems, **Load** it into the destination in a relatively raw/lightly-processed form, then **Transform** it _within_ the destination system itself, using that system's own query/compute capability.
- Modern cloud data warehouses and query engines (Redshift, and — relevant to this Part — Athena via CTAS queries, §101 §7.2) have become powerful and cost-effective enough that transforming data _after_ loading, using SQL running directly against the destination, is now a genuinely common and often simpler alternative to a separate upstream ETL processing step.
- Best fit: when the destination has ample compute capacity to handle transformation itself (Redshift, Athena/Spark), when transformation logic benefits from being expressed in the same SQL environment analysts will query with, or when minimizing the number of distinct processing systems/tools in the pipeline is itself a valued simplification.

### 5.3 ETL vs. ELT — Decision Framework

| Consideration                      | Favors ETL                                                                                     | Favors ELT                                                                                     |
| ---------------------------------- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Transformation complexity          | Complex, multi-source, custom-code logic (favors dedicated Spark processing — Glue Job or EMR) | Straightforward, SQL-expressible transformation                                                |
| Reuse across many consumers        | Transform once centrally, many consumers read the already-clean result                         | Each consumer might transform slightly differently for their own need                          |
| Destination compute capacity       | Destination has limited compute for heavy transformation                                       | Destination (Redshift, Athena) has ample compute to transform post-load                        |
| Governance/consistency requirement | Centralizing transformation logic ensures every consumer sees identically-processed data       | Less critical if transformation variance across consumers is acceptable                        |
| Tooling simplicity preference      | N/A                                                                                            | Fewer distinct systems (extract+load only, transform reuses the query engine already in place) |

- 🔑 **Key takeaway:** this Part's raw→curated pattern (§99) is fundamentally ETL-oriented (Glue Jobs/EMR transform _before_ the curated zone is queried) — but Athena's CTAS capability (§101 §7.2) is a genuinely ELT-style alternative for simpler transformations, meaning this Part's services support _both_ patterns, and the right choice is workload-dependent, not a fixed architectural commitment for an entire organization.

## 6. Common Combined Architectures (Not Either/Or)

- **Classic lake + warehouse hybrid:** raw/curated data lake (§99) feeding both Athena for ad hoc analysis and Redshift (with hot data loaded locally, cold data Spectrum-queried, §103) for BI reporting — the most common real-world pattern predating widespread lakehouse adoption, and still entirely valid for workloads without genuine transactional requirements.
- **Lakehouse-centralized:** an Iceberg (or similar) table format as the single source of truth, queried directly by Athena, EMR, and Redshift Spectrum alike, without needing to separately load a copy into Redshift's proprietary storage at all — an increasingly common pattern specifically as lakehouse table-format support matures across AWS's query engines, since it removes the "should this data live in the lake or the warehouse" question by making the lakehouse table queryable with warehouse-like performance/consistency directly.
- **Lake feeding search:** the same curated data lake also feeding OpenSearch (§105) for full-text/log-analytics use cases the SQL-oriented engines aren't built for — data lake curation (§1) and specialized search indexing aren't competing choices, they're complementary consumers of the same upstream raw/curated pipeline.

## 7. Common Mistakes in This Decision

- ❌ Adopting a lakehouse table format (Iceberg/Hudi/Delta Lake) for every table by default, including purely append-only tables with no transactional requirement, taking on the format's added complexity without a corresponding need for the transactional guarantees it provides.
- ❌ Defaulting to heavyweight ETL (a full EMR job) for a transformation that a simple Athena CTAS query (ELT-style) would have handled with far less operational overhead.
- ❌ Treating "data lake" and "data warehouse" as a permanent, exclusive architectural choice for an entire organization, rather than recognizing — as §6 demonstrates — that real architectures commonly combine multiple patterns for different workloads' different needs.
- ❌ Building a lakehouse-style pipeline without first confirming the specific query engines involved actually have mature support for the chosen table format at the organization's AWS service versions — an area that, per §4.2's warning, genuinely continues to evolve.

## 8. Interview Questions with Model Answers

**🎯 Junior:** _"In one sentence, what problem does the data lakehouse pattern solve?"_
**Model answer:** It combines a data lake's cheap, flexible, multi-engine-queryable storage (S3, open file formats) with the transactional guarantees — reliable row-level updates/deletes, consistent snapshots — that traditional data warehouses provide but plain data lake storage historically didn't, using an open table-format layer like Apache Iceberg on top of the underlying Parquet files.

**🎯 Intermediate:** _"A team needs to implement GDPR-style 'delete this specific customer's data' requests against their data lake, currently plain partitioned Parquet files in S3. Why is this hard with their current architecture, and what would you propose?"_
**Model answer:** Plain Parquet files in S3, cataloged via Glue (§99), don't natively support reliable row-level deletes — deleting specific rows matching a customer ID would typically mean rewriting entire affected Parquet files (or even entire partitions) from scratch, which is awkward, error-prone under concurrent access, and doesn't provide the kind of atomic, reliable guarantee a compliance requirement like this really needs. I'd propose adopting a lakehouse table format — Apache Iceberg being a strong, well-integrated choice — for this specific table, which adds the metadata layer needed to support genuine, atomic row-level deletes directly against the underlying S3 data, queryable through the same engines (Athena, in particular) the team already uses, without needing to migrate the data into a completely different storage system just to get this transactional capability.

**🎯 Senior:** _"Your organization currently uses heavyweight EMR Spark jobs for every data transformation, regardless of complexity, and the data platform team is stretched thin maintaining all of them. How would you evaluate which ones could be simplified?"_
**Model answer:** I'd review each existing EMR job's actual transformation logic against the ETL/ELT decision framework (§5.3) — specifically, whether the transformation is genuinely complex custom logic that needs Spark's programmatic flexibility, or whether it's actually a straightforward, SQL-expressible transformation (filtering, aggregation, format conversion, simple joins) that ended up on EMR more by historical default or team habit than genuine necessity. For jobs falling into that second category, converting them to an Athena CTAS query (§101 §7.2) — an ELT-style approach running the transformation as SQL against the query engine directly — would eliminate the ongoing EMR cluster-configuration and job-maintenance burden for those specific pipelines, directly reducing the platform team's maintenance load, while reserving the genuinely complex, EMR-justified transformations (custom Python/ML logic, multi-stage processing that doesn't map cleanly to SQL) for continued EMR investment. This is exactly the kind of right-sizing decision §102's Senior interview answer addressed from the cost/performance angle — here applied specifically to reducing ongoing human maintenance burden across a portfolio of existing pipelines, not just individual job cost.

**🎯 Architect:** _"Design the data architecture for a fast-growing fintech company that currently has a mix of ad hoc Athena queries against raw JSON, a growing Redshift cluster loaded with increasingly stale data, and a compliance requirement to support row-level data deletion requests across all historical transaction data — while keeping the architecture maintainable by a small data platform team."_
**Model answer:** Consolidate around a lakehouse-centralized pattern (§6) as the foundation: migrate the raw JSON data into a properly curated (§99), Iceberg-format (§4) table structure in S3, cataloged via Glue and governed via Lake Formation (§100) — this single change directly addresses three problems simultaneously: replacing ad hoc queries against raw JSON with fast, partitioned, columnar Athena queries (§99/§3's established performance benefit), providing the transactional row-level delete capability the compliance requirement needs (§4.3's exact fit case) without a separate compliance-specific system, and — critically for the "small team" constraint — reducing the number of genuinely distinct systems the team must operate, compared to maintaining separate raw-JSON, Redshift-loaded, and compliance-deletion-capable data paths independently. For the Redshift cluster specifically, apply §103's hot/cold pattern: rather than continuing to grow an increasingly stale, expensive local-storage footprint, keep only recent, actively-dashboarded data loaded locally, and query the new Iceberg-format historical data via Redshift Spectrum — this both controls Redshift cost/staleness and means the historical data (including anything subject to a future deletion request) lives in exactly one place — the Iceberg lakehouse table — rather than being duplicated and potentially inconsistently deleted across both Redshift's local storage and the data lake. For the ETL/ELT question specifically, favor ELT (Athena CTAS or simple Glue Jobs) for the straightforward JSON-to-Iceberg curation transformation, reserving any more complex processing (if it emerges as the company scales) for EMR — directly serving the "maintainable by a small team" constraint by defaulting to the lower-operational-overhead pattern unless genuine complexity requires otherwise.

## 9. Common Misconceptions

- "A data lakehouse is a specific AWS product you provision." False — it's an architectural pattern, built by combining S3 storage, an open-source table format (Iceberg/Hudi/Delta Lake), the Glue Data Catalog, and existing query engines (Athena, EMR, Redshift Spectrum); there's no single "Lakehouse" service to launch.
- "ELT is strictly newer and better than ETL, and should always be preferred." False — both remain legitimate, workload-dependent choices (§5.3); ETL remains the better fit for complex, reusable, centrally-governed transformation logic, while ELT fits simpler, SQL-expressible transformations well.
- "Adopting a lakehouse table format is only relevant for very large organizations." Overstated — the specific trigger is a genuine transactional requirement (row-level updates/deletes, concurrent-writer consistency), which can arise at moderate scale too (the GDPR-deletion example above), not solely a function of organization size.

## 10. Key Takeaways

🔑 The data lakehouse pattern combines data lake storage flexibility with warehouse-like transactional guarantees via an open table-format layer (commonly Apache Iceberg) — it's an architectural pattern built from existing services, not a distinct AWS product.
🔑 Choose a lakehouse table format specifically when genuine transactional requirements (row-level updates/deletes, concurrent-writer consistency, reliable snapshots) exist — not by default for every table.
🔑 ETL (transform before loading, via Glue Jobs/EMR) suits complex, reusable, centrally-governed transformation logic; ELT (transform after loading, via SQL/CTAS against the query engine) suits simpler, SQL-expressible transformation with less operational overhead.
🔑 Real production architectures commonly combine multiple patterns — lake+warehouse hybrids, lakehouse-centralized designs, and lake-feeding-search architectures — rather than committing to one pattern exclusively across an entire organization.
🔑 This synthesis directly closes the loop on every service introduced in §99-105: each solves one piece of a coherent, composable data engineering architecture, not a set of independent, unrelated tools.

## 11. Related Concepts

- Every service synthesized here: **Glue Data Catalog** (§99), **Lake Formation** (§100), **Athena** (§101), **EMR** (§102), **Redshift Spectrum** (§103), **QuickSight** (§104), **OpenSearch Service** (§105).
- **Amazon Redshift** (§55) — the traditional warehouse half of the lake/warehouse hybrid and lakehouse comparison.
- **§107** (next, final section of this Part) will close out Data Engineering & Analytics with a wrap-up and interview drill synthesizing all eight preceding sections.
