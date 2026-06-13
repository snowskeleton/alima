import { ReactNode } from 'react';

interface AlertProps {
  type?: 'success' | 'error' | 'warning' | 'info';
  children: ReactNode;
  className?: string;
}

const styles = {
  success: 'bg-green-50 text-green-800 border-green-200',
  error: 'bg-red-50 text-red-800 border-red-200',
  warning: 'bg-yellow-50 text-yellow-800 border-yellow-200',
  info: 'bg-blue-50 text-blue-800 border-blue-200',
};

export function Alert({ type = 'info', children, className = '' }: AlertProps) {
  return (
    <div className={`rounded-md border px-4 py-3 text-sm ${styles[type]} ${className}`}>
      {children}
    </div>
  );
}
