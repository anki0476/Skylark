export type ThemePreference = 'light' | 'dark' | 'system';
export function readTheme():ThemePreference{try{const value=localStorage.getItem('skylark.theme');return value==='dark'||value==='system'?value:'light'}catch{return 'light'}}
export function applyTheme(preference:ThemePreference){document.documentElement.dataset.theme=preference==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):preference}
applyTheme(readTheme());
