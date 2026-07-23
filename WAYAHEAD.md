# Way Ahead · Anonymation

## Diagnóstico (Julio 2026)

El proyecto actual NO anonimiza documentos reales. Problemas comprobados:

1. **`FIELD_BOXES`** — coordenadas inventadas, no calibradas contra ningún documento real
2. **IA visión (Gemini/Groq)** — devuelve bounding boxes inconsistentes; no sirven para redactar con precisión
3. **OCR (Tesseract)** — falla con fotos de móvil (glare, sombras, rotación, perspectiva)
4. **Tests** — sólo imágenes sintéticas; no demuestran nada sobre documentos reales
5. **`/api/auto-redact`** — bypassa las reglas RGPD; depende 100% de IA

---

## Hito 0: Fundación (ahora)
### Logro: La app funciona SIN depender de IA para coordenadas

- [x] `field_templates.json` — coordenadas por tipo de documento (cargables sin tocar código)
- [x] Lookup por tipo de documento en lugar de FIELD_BOXES plano
- [x] Editor manual en frontend: dibujar rectángulos sobre la imagen
- [x] Flujo: subir → previsualizar con detección automática → ajustar manualmente → redactar → descargar
- [x] `/api/auto-redact` reparado: usa templates por tipo, IA solo para clasificación
- [ ] Tests con documentos reales escaneados (pendiente de conseguir muestras)

**Métrica de éxito:** Un usuario puede subir cualquier documento y redactar campos visualmente aunque la detección automática falle.

---

## Hito 1: Calibración (1-2 semanas)
### Logro: Las coordenadas por defecto aciertan en documentos bien encuadrados

- [ ] Conseguir 1 muestra real de cada tipo (DNI, NIE, Pasaporte, Carné, T. Sanitaria, Padrón, Residencia)
- [ ] Escanear en 300 DPI, encuadrado perfecto
- [ ] Medir coordenadas exactas de cada campo en píxeles
- [ ] Convertir a porcentajes y actualizar `field_templates.json`
- [ ] Verificar visualmente: overlay sobre la imagen coincide con los campos reales

**Métrica de éxito:** DNI real escaneado → detección automática → campos coloreados coinciden ±2% con la posición real.

---

## Hito 2: Captura robusta (2-4 semanas)
### Logro: Las fotos de móvil producen resultados aceptables

- [ ] Guía visual en cámara (marca de posición para encuadrar el documento)
- [ ] Detección de bordes del documento (para auto-encuadrar)
- [ ] Corrección de perspectiva (homography)
- [ ] Rotación automática (EXIF + detección de texto)
- [ ] Mejora de contraste antes de pasar a detección

**Métrica de éxito:** 8/10 fotos de DNI con móvil → campos detectados con error <5%.

---

## Hito 3: Modo híbrido completo (1-2 meses)
### Logro: Selección manual + detección automática + IA cooperan

- [ ] Pipeline por orden de prioridad:
      1. Template calibrado (si documento bien encuadrado)
      2. Selección manual (usuario dibuja)
      3. IA como asistente (sugiere campos, no bounding boxes)
- [ ] El usuario siempre puede corregir antes de redactar
- [ ] Feedback de confianza: "Alta" (template), "Media" (manual), "Baja" (IA)
- [ ] Modo "sólo manual" para documentos genéricos (facturas, contratos)

**Métrica de éxito:** 3 modos funcionales, el usuario elige según su caso.

---

## Hito 4: Modelo ML especializado (2-3 meses)
### Logro: Detección local sin API externa, sin coste recurrente

- [ ] Fine-tune YOLOv8 o DETR con 100-200 imágenes anotadas de documentos reales
- [ ] Inferencia con ONNX Runtime (CPU, ~100ms por imagen)
- [ ] Reemplaza templates como método principal
- [ ] Templates como respaldo cuando el modelo no tiene confianza

**Métrica de éxito:** mAP@0.5 > 0.90 en documentos de test. Sin llamadas a APIs externas.

---

## Hito 5: Producción (3-4 meses)
### Logro: Despliegue real con usuarios

- [ ] Limpieza de archivos temporales (cron / celery beat)
- [ ] Rate limiting (flask-limiter)
- [ ] Logs estructurados (structlog)
- [ ] Healthcheck endpoint
- [ ] Tests en CI/CD (GitHub Actions)
- [ ] Documentación de usuario
- [ ] Panel de admin para gestión de API keys

---

## Principios rectores

1. **Primero lo que funciona, luego lo perfecto.** Manual > Template calibrado > ML > IA generalista.
2. **Sin documentos reales no hay mejora.** Cada hito requiere validación con documentos auténticos.
3. **El usuario siempre tiene el control.** La IA sugiere, el usuario decide.
4. **Sin almacenamiento de datos.** Procesamiento en memoria, cleanup inmediato.
5. **Minimización de dependencias externas.** APIs de IA son respaldo, no núcleo.

---

## Riesgos identificados

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| No conseguir documentos reales para calibrar | Alto | Usar modo manual como predeterminado |
| Gemini/Groq cambian precios o términos | Medio | La IA no es crítica en el nuevo diseño |
| DNI 4.0 cambia layout | Medio | Templates versionados por año/modelo |
| Usuarios fotografían mal el documento | Alto | Guías visuales + detección de bordes (Hito 2) |
