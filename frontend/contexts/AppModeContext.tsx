import React, { createContext, useContext, useState } from 'react';

type AppMode = 'parent' | 'child';

interface AppModeContextType {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  selectedProfile: string | null;
  setSelectedProfile: (profileId: string | null) => void;
}

const AppModeContext = createContext<AppModeContextType | undefined>(undefined);

export function AppModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<AppMode>('parent');
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);

  return (
    <AppModeContext.Provider value={{ mode, setMode, selectedProfile, setSelectedProfile }}>
      {children}
    </AppModeContext.Provider>
  );
}

export function useAppMode() {
  const context = useContext(AppModeContext);
  if (context === undefined) {
    throw new Error('useAppMode must be used within an AppModeProvider');
  }
  return context;
}
