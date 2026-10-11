import { House, ScanSearch, ChartNoAxesCombined, RadioTower, FlaskConical } from 'lucide-react';
import { Button } from './components/ui/button';

interface MobileNavigationProps {
  currentSection: string;
  onSelect: (section: string) => void;
}

const tabs = [
  { section: 'Resumen', label: 'Inicio', Icon: House },
  { section: 'PantheraID', label: 'PantheraID', Icon: ScanSearch },
  { section: 'PantheraMONITORING', label: 'Monitoreo', Icon: ChartNoAxesCombined },
  { section: 'PantheraEDGE', label: 'EDGE', Icon: RadioTower },
  { section: 'Investigación', label: 'Ciencia', Icon: FlaskConical },
] as const;

/** Phone-first bottom tabs; desktop retains its existing sidebar navigation. */
export default function MobileNavigation({ currentSection, onSelect }: MobileNavigationProps) {
  return <nav className="mobile-navigation" aria-label="Navegación móvil de PantheraLAB">
    {tabs.map(({ section, label, Icon }) => (
      <Button
        key={section}
        type="button"
        variant="ghost"
        className="mobile-tab"
        aria-label={section}
        aria-current={currentSection === section ? 'page' : undefined}
        onClick={() => {
          if (currentSection !== section) {
            onSelect(section);
            window.scrollTo({ top: 0, behavior: 'auto' });
          }
        }}
      >
        <Icon aria-hidden="true" size={21} strokeWidth={currentSection === section ? 2.3 : 1.8} />
        <span>{label}</span>
      </Button>
    ))}
  </nav>;
}
