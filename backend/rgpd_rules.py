from dataclasses import dataclass, field
from typing import Dict, List

@dataclass
class DocumentField:
    key: str
    label_es: str
    label_en: str
    strictly_necessary: bool
    sensitivity: str
    reason_if_excessive: str = ""

@dataclass
class DocumentType:
    code: str
    name_es: str
    name_en: str
    templates: List[str]
    aspect_ratio_range: tuple
    key_terms: List[str] = field(default_factory=list)
    fields: Dict[str, DocumentField] = field(default_factory=dict)

    def necessary_fields(self) -> Dict[str, DocumentField]:
        return {k: v for k, v in self.fields.items() if v.strictly_necessary}

    def excessive_fields(self) -> Dict[str, DocumentField]:
        return {k: v for k, v in self.fields.items() if not v.strictly_necessary}


DNI = DocumentType(
    code="dni",
    name_es="DNI / Documento Nacional de Identidad",
    name_en="Spanish National ID Card",
    templates=["DNI", "DOCUMENTO NACIONAL DE IDENTIDAD", "ESPANOLA", "IDENTIDAD",
               "DNIELECTRONICO", "DNI 3.0", "IDESP", "SOPORTE", "DNI DIGITAL"],
    key_terms=["DNI", "IDENTIDAD"],
    aspect_ratio_range=(0.60, 0.75),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de validez", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "dni_number": DocumentField("dni_number", "Numero de DNI", "ID number",
                                    strictly_necessary=False, sensitivity="high",
                                    reason_if_excessive="El numero completo no es necesario para la mayoria de tramites. Basta con los 4 ultimos digitos."),
        "address": DocumentField("address", "Direccion completa", "Full address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="La direccion domiciliaria no es necesaria a menos que el tramite requiera acreditacion de residencia."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria si el tramite requiere verificar mayoria de edad."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="El sexo no es relevante para la mayoria de tramites administrativos."),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=False, sensitivity="low",
                                     reason_if_excessive="Solo necesaria si el tramite requiere verificar nacionalidad."),
        "father_name": DocumentField("father_name", "Nombre del padre", "Father's name",
                                     strictly_necessary=False, sensitivity="medium",
                                     reason_if_excessive="Dato biometrico parental no necesario para identificacion."),
        "mother_name": DocumentField("mother_name", "Nombre de la madre", "Mother's name",
                                     strictly_necessary=False, sensitivity="medium",
                                     reason_if_excessive="Dato biometrico parental no necesario para identificacion."),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="La imagen de la firma es un dato biometrico sensible."),
    }
)

PASSPORT = DocumentType(
    code="passport",
    name_es="Pasaporte",
    name_en="Passport",
    templates=["PASAPORTE", "PASSPORT", "UNION EUROPEA", "EUROPEAN UNION",
               "VIAJE", "TRAVEL", "P<ESP", "PASAPORTE ELECTRONICO",
               "NACIONALIDAD", "APELLIDOS", "NOMBRE", "EXPEDIDO",
               "CADUCIDAD", "EXTRAORDINARIO"],
    key_terms=["PASAPORTE", "PASAPORTE ELECTRONICO", "TRAVEL DOCUMENT",
               "P<ESP", "P<"],
    aspect_ratio_range=(0.65, 0.80),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de caducidad", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=True, sensitivity="low"),
        "passport_number": DocumentField("passport_number", "Numero de pasaporte", "Passport number",
                                         strictly_necessary=False, sensitivity="high",
                                         reason_if_excessive="El numero de pasaporte completo es un identificador unico."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria para verificar mayoria de edad."),
        "pob": DocumentField("pob", "Lugar de nacimiento", "Place of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="El lugar de nacimiento es excesivo para la mayoria de tramites."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante para identificacion."),
        "height": DocumentField("height", "Altura", "Height",
                                strictly_necessary=False, sensitivity="low",
                                reason_if_excessive="Dato biometrico fisico no necesario."),
        "eye_color": DocumentField("eye_color", "Color de ojos", "Eye color",
                                   strictly_necessary=False, sensitivity="low",
                                   reason_if_excessive="Dato biometrico fisico no necesario."),
        "address": DocumentField("address", "Domicilio", "Address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="Direccion no necesaria si no se requiere acreditacion de residencia."),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="Dato biometrico sensible."),
        "authority": DocumentField("authority", "Autoridad de expedicion", "Issuing authority",
                                   strictly_necessary=False, sensitivity="low",
                                   reason_if_excessive="No necesario para validar la identidad."),
    }
)

DRIVING_LICENSE = DocumentType(
    code="driving_license",
    name_es="Carne de Conducir / Permiso de Circulacion",
    name_en="Driving License",
    templates=["CONDUCIR", "PERMISO", "LICENCIA", "CONDUCCION", "DRIVING",
               "LICENCE", "B1", "BTP", "REAL TRAFICO", "DGT", "TRAFICO",
               "CONDUCTOR", "VEHICULOS", "CATEGORIAS",
               "AUTORIZA", "REAL TRAFICO"],
    key_terms=["CONDUCIR", "DRIVING LICENCE", "DGT", "PERMISO CONDUCIR",
               "LICENCIA CONDUCIR", "TRAFICO"],
    aspect_ratio_range=(0.65, 0.75),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de validez", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "categories": DocumentField("categories", "Categorias (vehiculos)", "Categories (vehicles)",
                                    strictly_necessary=True, sensitivity="low"),
        "license_number": DocumentField("license_number", "Numero de permiso", "License number",
                                        strictly_necessary=False, sensitivity="high",
                                        reason_if_excessive="El numero completo no es necesario. Basta validar que el permiso es valido."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria para verificar mayoria de edad."),
        "pob": DocumentField("pob", "Lugar de nacimiento", "Place of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="No necesario para verificar permiso de conducir."),
        "address": DocumentField("address", "Direccion", "Address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="Direccion domiciliaria. Solo necesaria si es requisito del tramite."),
        "issuing_authority": DocumentField("issuing_authority", "Organo de expedicion", "Issuing authority",
                                           strictly_necessary=False, sensitivity="low",
                                           reason_if_excessive="No necesario para validar la identidad del titular."),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="Dato biometrico sensible."),
    }
)

NIE = DocumentType(
    code="nie",
    name_es="NIE / Numero de Identidad de Extranjero",
    name_en="Foreigner Identity Number (Spain)",
    templates=["NIE", "NUMERO DE IDENTIDAD DE EXTRANJERO", "EXTRANJERO",
               "IDENTIDAD EXTRANJERO", "TARJETA EXTRANJERO",
               "IDENTIDAD DE EXTRANJERO", "NUMERO NIE",
               "TARJETA DE IDENTIDAD"],
    key_terms=["NIE", "IDENTIDAD EXTRANJERO", "EXTRANJERO"],
    aspect_ratio_range=(0.60, 0.75),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de validez", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "nie_number": DocumentField("nie_number", "Numero de NIE", "NIE number",
                                    strictly_necessary=False, sensitivity="high",
                                    reason_if_excessive="El NIE completo es un identificador unico."),
        "address": DocumentField("address", "Direccion", "Address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="Direccion domiciliaria no necesaria sin acreditacion de residencia."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria si se requiere verificar mayoria de edad."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante para la mayoria de tramites."),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=False, sensitivity="low",
                                     reason_if_excessive="Solo si el tramite lo exige explicitamente."),
        "father_name": DocumentField("father_name", "Nombre del padre", "Father's name",
                                     strictly_necessary=False, sensitivity="medium",
                                     reason_if_excessive="Dato parental no necesario."),
        "mother_name": DocumentField("mother_name", "Nombre de la madre", "Mother's name",
                                     strictly_necessary=False, sensitivity="medium",
                                     reason_if_excessive="Dato parental no necesario."),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="Dato biometrico sensible."),
    }
)

RESIDENCE_CARD = DocumentType(
    code="residence_card",
    name_es="Tarjeta de Residencia / Residencia UE",
    name_en="Residence Card (EU/Spain)",
    templates=["RESIDENCIA", "TARJETA RESIDENCIA", "RESIDENCE", "RESIDENCIA UE",
               "FAMILIAR UE", "RESIDE", "PERMANENTE", "LARGA DURACION",
               "TARJETA DE RESIDENCIA", "PERMISO RESIDENCIA", "COMUNITARIO"],
    key_terms=["RESIDENCIA", "RESIDENCE", "FAMILIAR UE", "RESIDE"],
    aspect_ratio_range=(0.60, 0.75),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de validez", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "card_number": DocumentField("card_number", "Numero de tarjeta", "Card number",
                                     strictly_necessary=False, sensitivity="high",
                                     reason_if_excessive="El numero de tarjeta es un identificador unico no necesario."),
        "address": DocumentField("address", "Direccion", "Address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="Direccion domiciliaria. Solo necesaria si se requiere acreditar residencia."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria para verificar mayoria de edad."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante."),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=True, sensitivity="low"),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="Dato biometrico sensible."),
        "authority": DocumentField("authority", "Autoridad de expedicion", "Issuing authority",
                                   strictly_necessary=False, sensitivity="low",
                                   reason_if_excessive="No necesario para validar identidad."),
    }
)

HEALTH_CARD = DocumentType(
    code="health_card",
    name_es="Tarjeta Sanitaria / Seguridad Social",
    name_en="Health Card / Social Security Card",
    templates=["SANITARIA", "SEGURIDAD SOCIAL", "SALUD", "HEALTH", "TARJETA SANITARIA",
               "SNS", "SERVICIO SALUD", "T.S.I.", "ASEGURADO", "TARJETA INDIVIDUAL",
               "ASISTENCIA SANITARIA", "SANIDAD", "TARJETA SALUD"],
    key_terms=["SANITARIA", "SEGURIDAD SOCIAL", "TARJETA SANITARIA",
               "T.S.I.", "SNS", "ASISTENCIA SANITARIA"],
    aspect_ratio_range=(0.55, 0.70),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de validez", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "health_number": DocumentField("health_number", "Numero de afiliacion", "Health/SS number",
                                       strictly_necessary=False, sensitivity="high",
                                       reason_if_excessive="El numero de afiliacion es un identificador sanitario sensible."),
        "address": DocumentField("address", "Direccion", "Address",
                                 strictly_necessary=False, sensitivity="high",
                                 reason_if_excessive="Direccion domiciliaria no necesaria para asistencia sanitaria ordinaria."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria si el tramite lo requiere."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante para la mayoria de gestiones."),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=False, sensitivity="low",
                                     reason_if_excessive="No necesario para asistencia sanitaria."),
    }
)

PADRON = DocumentType(
    code="padron",
    name_es="Certificado de Empadronamiento",
    name_en="Municipal Registration Certificate",
    templates=["EMPADRONAMIENTO", "PADRON", "MUNICIPAL", "AYUNTAMIENTO",
               "CERTIFICADO EMPADRONAMIENTO", "HABITANTES",
               "CERTIFICADO DE EMPADRONAMIENTO", "PADRON MUNICIPAL",
               "CENSO", "HABITANTE"],
    key_terms=["EMPADRONAMIENTO", "PADRON MUNICIPAL", "CERTIFICADO EMPADRONAMIENTO",
               "AYUNTAMIENTO"],
    aspect_ratio_range=(0.65, 0.85),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "address": DocumentField("address", "Direccion completa", "Full address",
                                 strictly_necessary=True, sensitivity="low"),
        "issue_date": DocumentField("issue_date", "Fecha de expedicion", "Issue date",
                                    strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "dni_number": DocumentField("dni_number", "Numero de DNI/NIE", "ID number",
                                    strictly_necessary=False, sensitivity="high",
                                    reason_if_excessive="El certificado ya acredita residencia con nombre y direccion."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="No necesario para acreditar residencia."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante para certificado de empadronamiento."),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=False, sensitivity="low",
                                     reason_if_excessive="No necesario para acreditar residencia."),
        "previous_address": DocumentField("previous_address", "Domicilio anterior", "Previous address",
                                          strictly_necessary=False, sensitivity="high",
                                          reason_if_excessive="El domicilio anterior revela historico de residencia."),
    }
)

GENERIC_PASSPORT = DocumentType(
    code="generic_passport",
    name_es="Pasaporte (otros paises)",
    name_en="Passport (other countries)",
    templates=["PASSPORT", "PASAPORTE", "P<", "P<", "NATIONALITY",
               "FOREIGN", "PASAPORTE EXTRANJERO", "PASSPORT NO",
               "PASSPORT NUMBER", "DATE OF BIRTH", "PLACE OF BIRTH",
               "PASSPORT TYPE", "ISSUING COUNTRY"],
    key_terms=["PASSPORT", "P<", "NATIONALITY", "PASSPORT NUMBER",
               "DATE OF BIRTH", "PLACE OF BIRTH", "ISSUING COUNTRY"],
    aspect_ratio_range=(0.65, 0.80),
    fields={
        "full_name": DocumentField("full_name", "Nombre completo", "Full name",
                                   strictly_necessary=True, sensitivity="low"),
        "photo": DocumentField("photo", "Fotografia", "Photo",
                               strictly_necessary=True, sensitivity="low"),
        "expiration_date": DocumentField("expiration_date", "Fecha de caducidad", "Expiration date",
                                         strictly_necessary=True, sensitivity="low"),
        "document_type": DocumentField("document_type", "Tipo de documento", "Document type",
                                       strictly_necessary=True, sensitivity="low"),
        "nationality": DocumentField("nationality", "Nacionalidad", "Nationality",
                                     strictly_necessary=True, sensitivity="low"),
        "passport_number": DocumentField("passport_number", "Numero de pasaporte", "Passport number",
                                         strictly_necessary=False, sensitivity="high",
                                         reason_if_excessive="El numero de pasaporte completo es un identificador unico sensible."),
        "dob": DocumentField("dob", "Fecha de nacimiento", "Date of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="Solo necesaria para verificar mayoria de edad."),
        "pob": DocumentField("pob", "Lugar de nacimiento", "Place of birth",
                             strictly_necessary=False, sensitivity="medium",
                             reason_if_excessive="El lugar de nacimiento es excesivo para la mayoria de tramites."),
        "gender": DocumentField("gender", "Sexo", "Gender",
                                strictly_necessary=False, sensitivity="medium",
                                reason_if_excessive="No relevante."),
        "signature": DocumentField("signature", "Firma", "Signature",
                                   strictly_necessary=False, sensitivity="high",
                                   reason_if_excessive="Dato biometrico sensible."),
        "authority": DocumentField("authority", "Autoridad de expedicion", "Issuing authority",
                                   strictly_necessary=False, sensitivity="low",
                                   reason_if_excessive="No necesario."),
    }
)

DOCUMENT_TYPES = {
    "dni": DNI,
    "nie": NIE,
    "passport": PASSPORT,
    "generic_passport": GENERIC_PASSPORT,
    "driving_license": DRIVING_LICENSE,
    "residence_card": RESIDENCE_CARD,
    "health_card": HEALTH_CARD,
    "padron": PADRON,
}

# Maps AI field keys to system field keys so AI results can be used
# with FIELD_BOXES and RGPD rules.
AI_KEY_MAP = {
    "dni_number": "dni_number",
    "dni": "dni_number",
    "nie_number": "nie_number",
    "card_number": "card_number",
    "health_number": "health_number",
    "full_name": "full_name",
    "first_name": "full_name",
    "surnames": "full_name",
    "last_name": "full_name",
    "address": "address",
    "previous_address": "previous_address",
    "dob": "dob",
    "birth_date": "dob",
    "fecha_nacimiento": "dob",
    "gender": "gender",
    "sex": "gender",
    "sexo": "gender",
    "father_name": "father_name",
    "mother_name": "mother_name",
    "signature": "signature",
    "firma": "signature",
    "nationality": "nationality",
    "nacionalidad": "nationality",
    "passport_number": "passport_number",
    "pob": "pob",
    "birth_place": "pob",
    "lugar_nacimiento": "pob",
    "height": "height",
    "eye_color": "eye_color",
    "license_number": "license_number",
    "issuing_authority": "issuing_authority",
    "authority": "authority",
    "categories": "categories",
    "issue_date": "issue_date",
    "fecha_emision": "issue_date",
    "emision": "issue_date",
    "expiration_date": "expiration_date",
    "expiry_date": "expiration_date",
    "fecha_validez": "expiration_date",
    "validez": "expiration_date",
    "support_number": "dni_number",
    "num_sop": "dni_number",
    "num_soporte": "dni_number",
    "photo": "photo",
    "document_type": "document_type",
}

# List of AI keys that represent sub-fields of a composite field.
# When mapped, their boxes should be merged into the target field.
AI_COMPOSITE_KEYS = {"first_name", "surnames", "last_name"}


def map_ai_key(ai_key: str) -> str | None:
    return AI_KEY_MAP.get(ai_key)


def get_document_type(code: str) -> DocumentType:
    return DOCUMENT_TYPES.get(code)

def analyze_necessity(doc_type: DocumentType, purpose: str = "") -> dict:
    return {
        "document_type": doc_type.code,
        "document_name": doc_type.name_es,
        "total_fields": len(doc_type.fields),
        "necessary_fields": len(doc_type.necessary_fields()),
        "excessive_fields": len(doc_type.excessive_fields()),
        "fields": {
            k: {
                "label": v.label_es,
                "necessary": v.strictly_necessary,
                "sensitivity": v.sensitivity,
                "reason": v.reason_if_excessive,
            }
            for k, v in doc_type.fields.items()
        },
        "summary": (
            f"De {len(doc_type.fields)} campos detectados, "
            f"solo {len(doc_type.necessary_fields())} son estrictamente necesarios "
            f"segun el principio de minimizacion de datos (RGPD Art. 5). "
            f"Se recomienda redactar/tachar los {len(doc_type.excessive_fields())} campos restantes."
        ),
    }