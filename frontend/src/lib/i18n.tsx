import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useAuth } from "./auth";
import { api } from "./api";

export type Language = "en" | "ml" | "ta" | "pa" | "hi";
export const LANGUAGES: { code: Language; label: string; english: string }[] = [
  { code: "en", label: "English", english: "English" },
  { code: "ml", label: "മലയാളം", english: "Malayalam" },
  { code: "ta", label: "தமிழ்", english: "Tamil" },
  { code: "pa", label: "ਪੰਜਾਬੀ", english: "Punjabi" },
  { code: "hi", label: "हिन्दी", english: "Hindi" },
];

const messages: Record<Language, Record<string, string>> = {
  en: {
    "nav.overview":"Overview","nav.farms":"Farms & fields","nav.health":"Crop health","nav.harvest":"Harvest safety","nav.pollination":"Pollination","nav.produce":"Produce & buyers","nav.bookings":"Bookings","nav.services":"Services & availability","nav.demands":"Demand listings","nav.deliveries":"Deliveries","nav.review":"Review queue","nav.users":"Users & roles","nav.reference":"Reference data","nav.models":"Models","nav.audit":"Audit log","nav.plant":"Plant Intelligence",
    "account.settings":"Account settings","account.signout":"Sign out","notifications.title":"Notifications","notifications.empty":"Nothing new.","notifications.all":"View all",
    "language.label":"Language","language.saved":"Language preference saved","common.loading":"Loading…","common.save":"Save","common.cancel":"Cancel","common.back":"Back",
    "plant.title":"Plant Intelligence","plant.subtitle":"Track crop observations and care activities over time.","plant.select":"Select a crop","plant.observation":"Record observation","plant.activity":"Log activity","plant.timeline":"Crop timeline","plant.growth":"Growth stage","plant.height":"Plant height (cm)","plant.notes":"Notes","plant.source":"Measurement source","plant.manual":"Manual entry","plant.sensor":"Sensor reading","plant.weather":"Weather provider","plant.estimate":"Model estimate","plant.save":"Save record","plant.noRecords":"No observations yet. Add a verified observation to begin the timeline.","plant.noCrops":"No crop cycles are available for this account.","plant.evidence":"Recommendations are shown only when supported by configured crop guidance and recorded evidence."
  },
  ml: {
    "nav.overview":"അവലോകനം","nav.farms":"കൃഷിയിടങ്ങളും വയലുകളും","nav.health":"വിളയുടെ ആരോഗ്യം","nav.harvest":"വിളവെടുപ്പ് സുരക്ഷ","nav.pollination":"പരാഗണം","nav.produce":"വിളവും വാങ്ങുന്നവരും","nav.bookings":"ബുക്കിംഗുകൾ","nav.services":"സേവനങ്ങളും ലഭ്യതയും","nav.demands":"ആവശ്യ പട്ടികകൾ","nav.deliveries":"ഡെലിവറികൾ","nav.review":"പരിശോധന ക്യൂ","nav.users":"ഉപയോക്താക്കളും റോളുകളും","nav.reference":"റഫറൻസ് ഡാറ്റ","nav.models":"മോഡലുകൾ","nav.audit":"ഓഡിറ്റ് ലോഗ്","nav.plant":"സസ്യ നിരീക്ഷണം",
    "account.settings":"അക്കൗണ്ട് ക്രമീകരണങ്ങൾ","account.signout":"സൈൻ ഔട്ട്","notifications.title":"അറിയിപ്പുകൾ","notifications.empty":"പുതിയ അറിയിപ്പുകളില്ല.","notifications.all":"എല്ലാം കാണുക","language.label":"ഭാഷ",
    "common.loading":"ലോഡ് ചെയ്യുന്നു…","common.save":"സംരക്ഷിക്കുക","common.cancel":"റദ്ദാക്കുക","common.back":"തിരികെ",
    "plant.title":"സസ്യ നിരീക്ഷണം","plant.subtitle":"കാലക്രമത്തിൽ വിള നിരീക്ഷണങ്ങളും പരിപാലന പ്രവർത്തനങ്ങളും രേഖപ്പെടുത്തുക.","plant.select":"ഒരു വിള തിരഞ്ഞെടുക്കുക","plant.observation":"നിരീക്ഷണം രേഖപ്പെടുത്തുക","plant.activity":"പ്രവർത്തനം രേഖപ്പെടുത്തുക","plant.timeline":"വിളയുടെ സമയരേഖ","plant.growth":"വളർച്ചാ ഘട്ടം","plant.height":"ചെടിയുടെ ഉയരം (സെ.മീ.)","plant.notes":"കുറിപ്പുകൾ","plant.source":"അളവിന്റെ ഉറവിടം","plant.manual":"മാനുവൽ എൻട്രി","plant.sensor":"സെൻസർ വായന","plant.weather":"കാലാവസ്ഥാ സേവനം","plant.estimate":"മോഡൽ കണക്ക്","plant.save":"രേഖ സംരക്ഷിക്കുക","plant.noRecords":"ഇതുവരെ നിരീക്ഷണങ്ങളില്ല. സമയരേഖ ആരംഭിക്കാൻ സ്ഥിരീകരിച്ച നിരീക്ഷണം ചേർക്കുക.","plant.noCrops":"ഈ അക്കൗണ്ടിന് വിള ചക്രങ്ങൾ ലഭ്യമല്ല.","plant.evidence":"ക്രമീകരിച്ച വിള മാർഗ്ഗനിർദ്ദേശവും രേഖപ്പെടുത്തിയ തെളിവുകളും പിന്തുണയ്ക്കുമ്പോൾ മാത്രമേ നിർദ്ദേശങ്ങൾ കാണിക്കൂ."
  },
  ta: {
    "nav.overview":"கண்ணோட்டம்","nav.farms":"பண்ணைகள் மற்றும் வயல்கள்","nav.health":"பயிர் ஆரோக்கியம்","nav.harvest":"அறுவடை பாதுகாப்பு","nav.pollination":"மகரந்தச் சேர்க்கை","nav.produce":"விளைபொருட்கள் மற்றும் வாங்குபவர்கள்","nav.bookings":"முன்பதிவுகள்","nav.services":"சேவைகள் மற்றும் கிடைப்புத் தன்மை","nav.demands":"தேவைப் பட்டியல்கள்","nav.deliveries":"விநியோகங்கள்","nav.review":"மதிப்பாய்வு வரிசை","nav.users":"பயனர்கள் மற்றும் பங்குகள்","nav.reference":"குறிப்புத் தரவு","nav.models":"மாதிரிகள்","nav.audit":"தணிக்கை பதிவு","nav.plant":"தாவர நுண்ணறிவு",
    "account.settings":"கணக்கு அமைப்புகள்","account.signout":"வெளியேறு","notifications.title":"அறிவிப்புகள்","notifications.empty":"புதியவை எதுவும் இல்லை.","notifications.all":"அனைத்தையும் காண்க","language.label":"மொழி",
    "common.loading":"ஏற்றுகிறது…","common.save":"சேமி","common.cancel":"ரத்து செய்","common.back":"பின் செல்",
    "plant.title":"தாவர நுண்ணறிவு","plant.subtitle":"காலப்போக்கில் பயிர் கண்காணிப்புகளையும் பராமரிப்பு செயல்களையும் பதிவு செய்யுங்கள்.","plant.select":"பயிரைத் தேர்ந்தெடுக்கவும்","plant.observation":"கண்காணிப்பைப் பதிவு செய்","plant.activity":"செயலைப் பதிவு செய்","plant.timeline":"பயிர் காலவரிசை","plant.growth":"வளர்ச்சி நிலை","plant.height":"தாவர உயரம் (செ.மீ.)","plant.notes":"குறிப்புகள்","plant.source":"அளவீட்டு மூலம்","plant.manual":"கைமுறை பதிவு","plant.sensor":"சென்சார் அளவீடு","plant.weather":"வானிலை வழங்குநர்","plant.estimate":"மாதிரி மதிப்பீடு","plant.save":"பதிவைச் சேமி","plant.noRecords":"இன்னும் கண்காணிப்புகள் இல்லை. காலவரிசையைத் தொடங்க உறுதிப்படுத்தப்பட்ட கண்காணிப்பைச் சேர்க்கவும்.","plant.noCrops":"இந்தக் கணக்கிற்கு பயிர் சுழற்சிகள் இல்லை.","plant.evidence":"உள்ளமைக்கப்பட்ட பயிர் வழிகாட்டுதலும் பதிவுசெய்யப்பட்ட ஆதாரமும் உள்ளபோது மட்டுமே பரிந்துரைகள் காட்டப்படும்."
  },
  pa: {
    "nav.overview":"ਜਾਇਜ਼ਾ","nav.farms":"ਖੇਤ ਅਤੇ ਜ਼ਮੀਨ","nav.health":"ਫ਼ਸਲ ਦੀ ਸਿਹਤ","nav.harvest":"ਕਟਾਈ ਦੀ ਸੁਰੱਖਿਆ","nav.pollination":"ਪਰਾਗਣ","nav.produce":"ਉਪਜ ਅਤੇ ਖਰੀਦਦਾਰ","nav.bookings":"ਬੁਕਿੰਗਾਂ","nav.services":"ਸੇਵਾਵਾਂ ਅਤੇ ਉਪਲਬਧਤਾ","nav.demands":"ਮੰਗ ਸੂਚੀਆਂ","nav.deliveries":"ਡਿਲੀਵਰੀਆਂ","nav.review":"ਸਮੀਖਿਆ ਕਤਾਰ","nav.users":"ਵਰਤੋਂਕਾਰ ਅਤੇ ਭੂਮਿਕਾਵਾਂ","nav.reference":"ਹਵਾਲਾ ਡਾਟਾ","nav.models":"ਮਾਡਲ","nav.audit":"ਆਡਿਟ ਲਾਗ","nav.plant":"ਪੌਦਾ ਨਿਗਰਾਨੀ",
    "account.settings":"ਖਾਤਾ ਸੈਟਿੰਗਾਂ","account.signout":"ਸਾਈਨ ਆਉਟ","notifications.title":"ਸੂਚਨਾਵਾਂ","notifications.empty":"ਕੋਈ ਨਵੀਂ ਸੂਚਨਾ ਨਹੀਂ।","notifications.all":"ਸਭ ਵੇਖੋ","language.label":"ਭਾਸ਼ਾ",
    "common.loading":"ਲੋਡ ਹੋ ਰਿਹਾ ਹੈ…","common.save":"ਸੰਭਾਲੋ","common.cancel":"ਰੱਦ ਕਰੋ","common.back":"ਵਾਪਸ",
    "plant.title":"ਪੌਦਾ ਨਿਗਰਾਨੀ","plant.subtitle":"ਸਮੇਂ ਦੇ ਨਾਲ ਫ਼ਸਲ ਦੇ ਨਿਰੀਖਣ ਅਤੇ ਦੇਖਭਾਲ ਦਰਜ ਕਰੋ।","plant.select":"ਫ਼ਸਲ ਚੁਣੋ","plant.observation":"ਨਿਰੀਖਣ ਦਰਜ ਕਰੋ","plant.activity":"ਗਤੀਵਿਧੀ ਦਰਜ ਕਰੋ","plant.timeline":"ਫ਼ਸਲ ਸਮਾਂ-ਰੇਖਾ","plant.growth":"ਵਿਕਾਸ ਪੜਾਅ","plant.height":"ਪੌਦੇ ਦੀ ਉਚਾਈ (ਸੈ.ਮੀ.)","plant.notes":"ਨੋਟਸ","plant.source":"ਮਾਪ ਦਾ ਸਰੋਤ","plant.manual":"ਹੱਥੋਂ ਦਰਜ ਕੀਤਾ","plant.sensor":"ਸੈਂਸਰ ਰੀਡਿੰਗ","plant.weather":"ਮੌਸਮ ਸੇਵਾ","plant.estimate":"ਮਾਡਲ ਅਨੁਮਾਨ","plant.save":"ਰਿਕਾਰਡ ਸੰਭਾਲੋ","plant.noRecords":"ਹਾਲੇ ਕੋਈ ਨਿਰੀਖਣ ਨਹੀਂ। ਸਮਾਂ-ਰੇਖਾ ਸ਼ੁਰੂ ਕਰਨ ਲਈ ਪੁਸ਼ਟੀ ਕੀਤਾ ਨਿਰੀਖਣ ਜੋੜੋ।","plant.noCrops":"ਇਸ ਖਾਤੇ ਲਈ ਫ਼ਸਲ ਚੱਕਰ ਉਪਲਬਧ ਨਹੀਂ ਹਨ।","plant.evidence":"ਸਿਫ਼ਾਰਸ਼ਾਂ ਸਿਰਫ਼ ਤਦੋਂ ਦਿਖਾਈਆਂ ਜਾਂਦੀਆਂ ਹਨ ਜਦੋਂ ਫ਼ਸਲ ਮਾਰਗਦਰਸ਼ਨ ਅਤੇ ਦਰਜ ਸਬੂਤ ਉਪਲਬਧ ਹੋਣ।"
  },
  hi: {
    "nav.overview":"अवलोकन","nav.farms":"खेत और भूमि","nav.health":"फसल स्वास्थ्य","nav.harvest":"कटाई सुरक्षा","nav.pollination":"परागण","nav.produce":"उपज और खरीदार","nav.bookings":"बुकिंग","nav.services":"सेवाएँ और उपलब्धता","nav.demands":"मांग सूची","nav.deliveries":"डिलीवरी","nav.review":"समीक्षा कतार","nav.users":"उपयोगकर्ता और भूमिकाएँ","nav.reference":"संदर्भ डेटा","nav.models":"मॉडल","nav.audit":"ऑडिट लॉग","nav.plant":"पौधा निगरानी",
    "account.settings":"खाता सेटिंग","account.signout":"साइन आउट","notifications.title":"सूचनाएँ","notifications.empty":"कोई नई सूचना नहीं।","notifications.all":"सभी देखें","language.label":"भाषा",
    "common.loading":"लोड हो रहा है…","common.save":"सहेजें","common.cancel":"रद्द करें","common.back":"वापस",
    "plant.title":"पौधा निगरानी","plant.subtitle":"समय के साथ फसल के अवलोकन और देखभाल गतिविधियाँ दर्ज करें।","plant.select":"फसल चुनें","plant.observation":"अवलोकन दर्ज करें","plant.activity":"गतिविधि दर्ज करें","plant.timeline":"फसल समयरेखा","plant.growth":"विकास चरण","plant.height":"पौधे की ऊँचाई (सेमी)","plant.notes":"टिप्पणियाँ","plant.source":"मापन स्रोत","plant.manual":"मैन्युअल प्रविष्टि","plant.sensor":"सेंसर रीडिंग","plant.weather":"मौसम प्रदाता","plant.estimate":"मॉडल अनुमान","plant.save":"रिकॉर्ड सहेजें","plant.noRecords":"अभी कोई अवलोकन नहीं है। समयरेखा शुरू करने के लिए सत्यापित अवलोकन जोड़ें।","plant.noCrops":"इस खाते के लिए फसल चक्र उपलब्ध नहीं हैं।","plant.evidence":"सिफ़ारिशें तभी दिखाई जाती हैं जब फसल-विशिष्ट मार्गदर्शन और दर्ज साक्ष्य उपलब्ध हों।"
  }
};

type I18nContextValue = { language: Language; setLanguage: (language: Language) => void; t: (key: string) => string };
const I18nContext = createContext<I18nContextValue>({ language: "en", setLanguage: () => {}, t: (key) => messages.en[key] ?? key });

function validLanguage(value: string | null): Language {
  return value === "ml" || value === "ta" || value === "pa" || value === "hi" ? value : "en";
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(() => validLanguage(localStorage.getItem("agastya-language")));
  const setLanguage = (next: Language) => {
    setLanguageState(next);
    localStorage.setItem("agastya-language", next);
    document.documentElement.lang = next;
    window.dispatchEvent(new CustomEvent("agastya:language-changed", { detail: next }));
  };
  useEffect(() => { document.documentElement.lang = language; }, [language]);
  const value = useMemo(() => ({ language, setLanguage, t: (key: string) => messages[language][key] ?? messages.en[key] ?? key }), [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() { return useContext(I18nContext); }

export function LanguageSelect({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage } = useI18n();
  const { user } = useAuth();
  useEffect(() => {
    if (user?.preferred_language && user.preferred_language !== language) setLanguage(user.preferred_language);
  }, [user?.preferred_language]);
  const changeLanguage = (next: Language) => {
    setLanguage(next);
    if (user) api("/auth/me", { method: "PATCH", body: { preferred_language: next } }).catch(() => undefined);
  };
  return <label className="inline-flex items-center gap-2 text-sm text-muted">
    {!compact && <span>{messages[language]["language.label"] ?? "Language"}</span>}
    <select aria-label="Language" value={language} onChange={(e) => changeLanguage(e.target.value as Language)} className="rounded-md border border-line bg-paper px-2 py-1.5 text-sm text-charcoal">
      {LANGUAGES.map((lang) => <option key={lang.code} value={lang.code}>{lang.label}</option>)}
    </select>
  </label>;
}
