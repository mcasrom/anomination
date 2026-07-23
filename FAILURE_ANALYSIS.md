# Análisis de Fallos · Anonymation

## Resumen de resultados (Julio 2026)

### Muestra: 3 documentos reales fotografiados con smartphone

| Archivo | Resultado | Píxeles redactados |
|---------|-----------|-------------------|
| `b8ff...` | Aceptable (parcial) | 31.4% |
| `cabe2...` | INACEPTABLE (lo tacha todo) | 83.3% |
| `7f85...` | Fallo parcial | 18.5% |
| `30f7...` | Fallo parcial | 17.2% |

## Diagnóstico técnico

### 1. Tesseract OCR no es suficiente para fotos de smartphone

Problemas observados:
- `12345678Z` → OCR lo lee como `128466782` (dígitos erróneos, pierde la letra)
- `15/03/1990` → OCR lo lee como `15/03/1890` (año incorrecto)
- `DNI` label → confianza 0% (Tesseract no reconoce texto estándar en documentos)
- Caracteres acentuados, glare, sombras, perspectiva → degradan la precisión

**Conclusión:** Tesseract fue diseñado para documentos escaneados planos en 300 DPI. 
Para fotos de smartphone se necesita un OCR de última generación.

### 2. El enfoque de labels + valores funciona en teoría pero no en la práctica

La detección por contenido (buscar label "DOMICILIO" → encontrar valor adyacente) 
es correcta CONCEPTUALMENTE pero falla porque:
- Tesseract no lee las labels correctamente en fotos reales
- Los bounding boxes de Tesseract son imprecisos
- La confianza varía enormemente entre capturas

### 3. Los templates estáticos no son viables

Cada documento tiene variaciones:
- Distintas versiones del DNI (3.0 vs 4.0, electrónico vs tradicional)
- Distintos formatos de pasaporte (español vs UE vs extracomunitario)
- Distintas orientaciones (retrato vs paisaje, según cómo se fotografíe)
- Distintas resoluciones y calidades de imagen

## Soluciones necesarias para producción

### Opción A: EasyOCR (recomendado, esfuerzo medio)

EasyOCR es significativamente mejor que Tesseract en fotos de móvil:
- Precisión ~90%+ en fotos de documentos (vs ~40-60% de Tesseract)
- Devuelve bounding boxes precisos con texto y confianza
- Soporta español e inglés nativamente
- Peso: ~100MB adicionales en el Docker

**Implementación:**
```python
import easyocr
reader = easyocr.Reader(['es', 'en'])
results = reader.readtext(image)
# results = [(bbox, text, confidence), ...]
```

### Opción B: YOLOv8 fine-tune (esfuerzo alto, mejor resultado)

Entrenar un modelo de detección de objetos con:
- 50-100 fotos de DNIs reales anotadas con LabelStudio
- Clases: dni_number, full_name, photo, address, signature, dob...
- Inferencia en CPU con ONNX (~50-100ms por imagen)
- Sin dependencia de APIs externas

### Opción C: Google/Azure Document AI (esfuerzo bajo, coste recurrente)

APIs especializadas en documentos de identidad:
- Google Document AI: Identity Processor (~$0.05/doc)
- Azure Document Intelligence: prebuilt-idDocument (~$0.02/doc)

## Qué conservar del trabajo actual

- **Reglas RGPD** (`rgpd_rules.py`): correctas y completas (8 tipos de documento)
- **Editor manual en frontend**: funcional, necesario como respaldo
- **Referencias legales**: AEPD, INCIBE, RGPD Art. 5, LOPDGDD, ENS
- **Estructura de templates** (`field_templates.json`): útil como respaldo cuando OCR no funciona
- **Pipeline de detección por contenido**: el enfoque conceptual es correcto, el problema es Tesseract

## Próximos pasos (cuando se retome)

1. Reemplazar Tesseract por **EasyOCR** en `document_analyzer.py`
2. Mantener label-based detection (funciona igual pero con OCR mejorado)
3. Templates como fallback para signature y photo
4. Probar con los mismos documentos del usuario para validar mejora
5. Si EasyOCR no es suficiente → migrar a YOLOv8 o Document AI
