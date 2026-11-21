"""
Замяна на имената на учителите с кодове („Учител-3“), преди текст да отиде
към външния езиков модел (въпрос 12 от плана). След отговора кодовете се
връщат обратно в имена. Така моделът никога не вижда истински имена.
"""
import re


class TeacherCodes:
    def __init__(self, names):
        self.name_to_code = {name: f"Учител-{i}" for i, name in enumerate(sorted(names), start=1)}
        self.code_to_name = {code: name for name, code in self.name_to_code.items()}

        # Освен пълното име разпознаваме и фамилията или първото име, ако е еднозначно.
        parts = {}
        for name in names:
            for part in name.split():
                parts.setdefault(part.lower(), set()).add(name)
        self.part_to_code = {part: self.name_to_code[next(iter(owners))]
                             for part, owners in parts.items() if len(owners) == 1 and len(part) > 2}

    def hide(self, text):
        """Заменя имената в свободен текст (напр. въпроса на потребителя) с кодове."""
        for name, code in sorted(self.name_to_code.items(), key=lambda item: -len(item[0])):
            text = re.sub(re.escape(name), code, text, flags=re.IGNORECASE)
        for part, code in self.part_to_code.items():
            text = re.sub(rf"\b{re.escape(part)}\b", code, text, flags=re.IGNORECASE)
        return text

    def reveal(self, text):
        """Връща кодовете в имена (в отговора на модела)."""
        # Първо по-дългите кодове, за да не се сбърка „Учител-1“ с „Учител-12“.
        for code, name in sorted(self.code_to_name.items(), key=lambda item: -len(item[0])):
            text = text.replace(code, name)
        return text

    def hide_data(self, value):
        """Заменя имената навсякъде в данните от справка (речници, списъци, текст)."""
        if isinstance(value, dict):
            return {key: self.hide_data(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.hide_data(item) for item in value]
        if isinstance(value, str):
            return self.name_to_code.get(value, value)
        return value

    def reveal_data(self, value):
        """Обратното на hide_data – за параметрите, които моделът е избрал."""
        if isinstance(value, dict):
            return {key: self.reveal_data(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.reveal_data(item) for item in value]
        if isinstance(value, str):
            return self.reveal(value)
        return value
