/*
 * leads-priorizacion — DDL para Supabase (PostgreSQL 15+)
 * ────────────────────────────────────────────────────────
 * Esquema normalizado para el pipeline de priorización de leads.
 *
 * Convenciones:
 *   • PKs textuales conservan el formato del negocio (EMP-01, PV-002…).
 *   • La tabla `lead` usa UUID porque los registros se deduplicaron/fusionaron
 *     y el array lead_id_original[] guarda los IDs crudos originales.
 *   • Timestamps con zona horaria (TIMESTAMPTZ) — Colombia = America/Bogota.
 *   • RLS al final del archivo, separado del DDL estructural.
 */

-- ============================================================
-- 0. Extensiones requeridas
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()


-- ============================================================
-- 1. empresa
--    Razón social de cada concesionario (EMP-01, EMP-02, EMP-03).
-- ============================================================
CREATE TABLE empresa (
    empresa_id   TEXT        PRIMARY KEY,
    nombre       TEXT        NOT NULL,
    nit          TEXT        UNIQUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 2. punto_venta
--    Sede física de un concesionario; cada una pertenece a una empresa.
-- ============================================================
CREATE TABLE punto_venta (
    punto_venta_id  TEXT        PRIMARY KEY,
    empresa_id      TEXT        NOT NULL REFERENCES empresa(empresa_id),
    nombre          TEXT,
    ciudad          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_punto_venta_empresa ON punto_venta(empresa_id);


-- ============================================================
-- 3. asesor
--    Asesor comercial asignado a un punto de venta.
-- ============================================================
CREATE TABLE asesor (
    asesor_id              TEXT        PRIMARY KEY,
    nombre                 TEXT        NOT NULL,
    punto_venta_id         TEXT        NOT NULL REFERENCES punto_venta(punto_venta_id),
    empresa_id             TEXT        NOT NULL REFERENCES empresa(empresa_id),
    capacidad_diaria_leads INTEGER     NOT NULL DEFAULT 15,
    activo                 BOOLEAN     NOT NULL DEFAULT TRUE,
    fecha_ingreso          DATE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_asesor_empresa ON asesor(empresa_id);


-- ============================================================
-- 4. moto_catalogo
--    Catálogo de motos disponibles con precio de lista y stock.
-- ============================================================
CREATE TABLE moto_catalogo (
    sku                        TEXT        PRIMARY KEY,
    marca                      TEXT        NOT NULL,
    linea                      TEXT        NOT NULL,
    cilindraje                 INTEGER,
    segmento                   TEXT,
    precio_lista               NUMERIC(12, 0),
    puntos_venta_disponibles   TEXT[],      -- Array de punto_venta_id
    unidades_disponibles       INTEGER     NOT NULL DEFAULT 0,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 5. lead
--    Lead normalizado y deduplicado.  Cuando el pipeline detecta
--    que varios registros crudos son la misma persona (mismo
--    teléfono normalizado, por ejemplo) los fusiona en una sola
--    fila y guarda todos los IDs originales en lead_id_original[].
-- ============================================================
CREATE TABLE lead (
    lead_id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id_original       TEXT[]      NOT NULL,          -- p.ej. {'LD-00042','LD-01310'}

    -- Temporalidad
    fecha_registro         TIMESTAMPTZ NOT NULL,
    fecha_primer_contacto  TIMESTAMPTZ,

    -- Origen
    canal                  TEXT        NOT NULL,          -- 'WhatsApp' | 'Meta Ads' | 'Formulario Web'
    campania               TEXT,

    -- Empresa / punto de venta
    empresa_id             TEXT        NOT NULL REFERENCES empresa(empresa_id),
    punto_venta_id         TEXT        REFERENCES punto_venta(punto_venta_id),

    -- Datos de contacto (normalizados)
    nombre_cliente         TEXT        NOT NULL,
    telefono_normalizado   TEXT,                          -- 10 dígitos sin prefijo país
    telefono_original      TEXT,                          -- Tal cual vino en el CSV
    email                  TEXT,
    ciudad                 TEXT,

    -- Interés en producto
    modelo_interes_texto   TEXT,                          -- Texto libre del lead
    sku_match              TEXT        REFERENCES moto_catalogo(sku),  -- Match al catálogo

    -- Estado
    estado_gestion         TEXT        NOT NULL,          -- Normalizado: 'Contactado', 'Sin gestión'…
    es_descartado          BOOLEAN     NOT NULL DEFAULT FALSE, -- Registro de prueba/basura

    -- Auditoría
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices solicitados explícitamente
CREATE INDEX idx_lead_empresa        ON lead(empresa_id);
CREATE INDEX idx_lead_telefono_norm  ON lead(telefono_normalizado);

-- Índices complementarios útiles para queries del dashboard
CREATE INDEX idx_lead_estado         ON lead(estado_gestion);
CREATE INDEX idx_lead_fecha_registro ON lead(fecha_registro);
CREATE INDEX idx_lead_sku_match      ON lead(sku_match)       WHERE sku_match IS NOT NULL;


-- ============================================================
-- 6. lead_enriquecido
--    Resultado de la extracción con IA (Claude) sobre las
--    conversaciones asociadas al lead.  Relación 1:1 con lead.
-- ============================================================
CREATE TABLE lead_enriquecido (
    lead_enriquecido_id    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id                UUID        NOT NULL UNIQUE REFERENCES lead(lead_id) ON DELETE CASCADE,

    -- Señales extraídas por IA de la conversación
    intencion_compra       TEXT,       -- 'Alta' | 'Media' | 'Baja' | 'Solo cotización'
    forma_pago_declarada   TEXT,       -- 'Contado' | 'Crédito' | 'No informa'
    monto_cuota_inicial    NUMERIC(12, 0),  -- NULL si no aplica / no mencionó
    pidio_cita             BOOLEAN,
    objeciones             TEXT[],     -- p.ej. {'precio alto','no tiene cuota inicial'}
    marcas_competencia     TEXT[],     -- Marcas rivales mencionadas
    urgencia               TEXT,       -- 'Inmediata' | 'Esta semana' | 'Explorando'
    resumen_conversacion   TEXT,       -- Resumen generado por IA

    -- Metadatos del procesamiento
    modelo_ia              TEXT        NOT NULL,  -- p.ej. 'claude-sonnet-4-20250514'
    tokens_usados          INTEGER,
    procesado_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 7. lead_score
--    Puntaje de priorización calculado para cada lead, con la
--    justificación en texto plano para que el asesor entienda
--    por qué ese lead está arriba o abajo en la lista.
-- ============================================================
CREATE TABLE lead_score (
    lead_score_id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID        NOT NULL UNIQUE REFERENCES lead(lead_id) ON DELETE CASCADE,

    score           NUMERIC(5, 2) NOT NULL,    -- 0.00 – 100.00
    prioridad       TEXT          NOT NULL,     -- 'Alta' | 'Media' | 'Baja'
    justificacion   TEXT          NOT NULL,     -- Explicación legible para el asesor

    -- Desglose de factores (permite debug y transparencia)
    factor_canal           NUMERIC(4, 2),
    factor_tiempo_resp     NUMERIC(4, 2),
    factor_intencion       NUMERIC(4, 2),
    factor_forma_pago      NUMERIC(4, 2),
    factor_engagement      NUMERIC(4, 2),

    -- Metadatos
    version_modelo  TEXT          NOT NULL DEFAULT 'v1',
    calculado_at    TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE INDEX idx_lead_score_prioridad ON lead_score(prioridad);
CREATE INDEX idx_lead_score_score     ON lead_score(score DESC);


-- ============================================================
-- 8. Row Level Security (RLS)
-- ============================================================
/*
 * ESTRATEGIA DE AISLAMIENTO POR EMPRESA
 * ──────────────────────────────────────
 * Cada sesión de PostgreSQL declara a qué empresa pertenece el
 * usuario conectado mediante:
 *
 *     SET LOCAL "app.empresa_actual" = 'EMP-01';
 *
 * Las policies comparan esa variable con la columna empresa_id
 * de cada fila.  Para lead_enriquecido y lead_score (que no
 * tienen empresa_id propia) la policy hace un sub-select contra
 * la tabla lead — un "join implícito" transparente.
 *
 * ¿CÓMO LO USA EL DASHBOARD DE STREAMLIT?
 * ─────────────────────────────────────────
 * El dashboard se conecta a Supabase con la clave `anon`
 * (supabase.create_client(url, anon_key)), que SÍ pasa por RLS.
 * Inmediatamente después de abrir la conexión, ejecuta:
 *
 *     SET LOCAL "app.empresa_actual" = '<empresa_id del usuario>';
 *
 * De esta forma cada empresa solo ve sus propios leads, scores
 * y enriquecimientos.
 *
 * ⚠ NUNCA usar la clave `service_role` desde el dashboard:
 *   esa clave bypasea RLS por completo y expondría datos de
 *   todas las empresas.  service_role se reserva exclusivamente
 *   para el pipeline de ETL que carga datos desde el backend.
 */

-- ── lead ──────────────────────────────────────────────────────
ALTER TABLE lead ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_isolation ON lead
    FOR ALL
    USING (
        empresa_id = current_setting('app.empresa_actual', true)
    )
    WITH CHECK (
        empresa_id = current_setting('app.empresa_actual', true)
    );

-- ── lead_enriquecido (join implícito a lead) ─────────────────
ALTER TABLE lead_enriquecido ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_enriquecido_isolation ON lead_enriquecido
    FOR ALL
    USING (
        lead_id IN (
            SELECT l.lead_id
              FROM lead l
             WHERE l.empresa_id = current_setting('app.empresa_actual', true)
        )
    )
    WITH CHECK (
        lead_id IN (
            SELECT l.lead_id
              FROM lead l
             WHERE l.empresa_id = current_setting('app.empresa_actual', true)
        )
    );

-- ── lead_score (join implícito a lead) ───────────────────────
ALTER TABLE lead_score ENABLE ROW LEVEL SECURITY;

CREATE POLICY lead_score_isolation ON lead_score
    FOR ALL
    USING (
        lead_id IN (
            SELECT l.lead_id
              FROM lead l
             WHERE l.empresa_id = current_setting('app.empresa_actual', true)
        )
    )
    WITH CHECK (
        lead_id IN (
            SELECT l.lead_id
              FROM lead l
             WHERE l.empresa_id = current_setting('app.empresa_actual', true)
        )
    );


-- ============================================================
-- 9. Trigger updated_at
--    Actualiza automáticamente lead.updated_at en cada UPDATE.
-- ============================================================
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER lead_set_updated_at
    BEFORE UPDATE ON lead
    FOR EACH ROW
    EXECUTE FUNCTION trg_set_updated_at();
