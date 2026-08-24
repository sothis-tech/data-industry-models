import { useTranslation } from "react-i18next";

const LANGS = [
  { code: "es", label: "Español" },
  { code: "en", label: "English" },
  { code: "ca", label: "Valencià" },
];

export function LanguageSelector() {
  const { i18n } = useTranslation();
  return (
    <select
      value={i18n.resolvedLanguage}
      onChange={(e) => i18n.changeLanguage(e.target.value)}
      aria-label="Idioma"
    >
      {LANGS.map((l) => (
        <option key={l.code} value={l.code}>{l.label}</option>
      ))}
    </select>
  );
}
