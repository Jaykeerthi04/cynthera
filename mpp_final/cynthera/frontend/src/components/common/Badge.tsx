import React from 'react';

export interface BadgeProps {
  variant?: 'support' | 'oppose' | 'uncertain' | 'neutral' | 'accent';
  children: React.ReactNode;
  icon?: React.ReactNode;
  title?: string;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  children,
  icon,
  title,
  className = '',
}) => {
  return (
    <span
      className={`badge badge-${variant} ${className}`}
      title={title}
      role="status"
    >
      {icon}
      <span>{children}</span>
    </span>
  );
};
