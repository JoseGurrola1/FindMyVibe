/**
 * A small orange tabby walking upright in boots: the loading animation.
 * Pure SVG + CSS (animations live in globals.css under "Walking cat"),
 * so there's no image to load and it stays sharp at any size.
 */
export default function WalkingCat({ size = 72, label = 'Loading' }: { size?: number; label?: string }) {
  const fur = '#e8892b';
  const furDark = '#c9661a';
  const cream = '#f7d29c';
  const boot = '#5e3618';
  const leather = '#8b5a2b';

  const leg = (cls: string, x: number) => (
    <g className={cls}>
      <rect x={x} y="62" width="7" height="16" rx="3.5" fill={fur} />
      {/* boot */}
      <path d={`M${x - 1} 74 h9 v6 q0 2 2 2 h4 q2 0 2 3 v1 h-17 z`} fill={boot} />
      <rect x={x - 1.5} y="73" width="10" height="2.5" rx="1.2" fill={leather} />
    </g>
  );

  return (
    <svg
      role="img"
      aria-label={label}
      width={size * (80 / 96)}
      height={size}
      viewBox="0 0 80 96"
      className="walking-cat inline-block"
    >
      {/* ground shadow */}
      <ellipse className="cat-shadow" cx="40" cy="90" rx="17" ry="2.6" fill="#7a4a22" opacity="0.18" />

      {/* far leg + far arm (behind the body) */}
      <g opacity="0.85">{leg('cat-leg cat-leg-back', 34)}</g>

      <g className="cat-bob">
        {/* tail */}
        <path className="cat-tail" d="M29 60 C 15 62, 9 50, 14 38 C 16 33, 20 32, 21 35"
              fill="none" stroke={fur} strokeWidth="5.5" strokeLinecap="round" />
        <path className="cat-tail" d="M14.5 44 l4 1.5 M13.5 51 l4.2 0.5" stroke={furDark} strokeWidth="1.6" strokeLinecap="round" />

        <g className="cat-arm cat-arm-back">
          <path d="M40 45 q-3 8 -3 14" fill="none" stroke={furDark} strokeWidth="5" strokeLinecap="round" />
        </g>

        {/* satchel on the far hip */}
        <rect x="23" y="58" width="10" height="9" rx="2.5" fill={leather} />
        <rect x="23" y="58" width="10" height="3.2" rx="1.6" fill={boot} />

        {/* body */}
        <ellipse cx="40" cy="55" rx="13" ry="15.5" fill={fur} />
        <ellipse cx="44.5" cy="58" rx="7" ry="10.5" fill={cream} />
        <path d="M29 49 q4 -1 6 2 M28.5 55 q4 -1 6 2 M29.5 61 q3.5 -0.6 5.5 1.6"
              fill="none" stroke={furDark} strokeWidth="1.7" strokeLinecap="round" />
        {/* satchel strap */}
        <path d="M33 59 L48 42" stroke={boot} strokeWidth="2.4" strokeLinecap="round" />

        {/* head */}
        <g className="cat-head">
          <path d="M37 23 L39.5 8.5 L47 17.5 Z" fill={fur} />
          <path d="M39.5 20 L40.6 12.5 L44.4 17.3 Z" fill="#f2a6a0" />
          <path d="M48 17 L55.5 9 L57 22 Z" fill={furDark} />
          <circle cx="47" cy="29" r="12.5" fill={fur} />
          <path d="M40 19.5 q2 3 1 6 M44.5 17.5 q1.4 3 0.3 6" fill="none" stroke={furDark} strokeWidth="1.6" strokeLinecap="round" />
          {/* muzzle, nose, mouth */}
          <ellipse cx="55.5" cy="33" rx="6" ry="4.6" fill={cream} />
          <path d="M60.2 29.8 l2.3 0.6 l-1.6 1.8 z" fill="#c4544a" />
          <path d="M60.8 32.4 q-0.6 2.4 -2.8 2.2" fill="none" stroke="#5a3418" strokeWidth="1" strokeLinecap="round" />
          {/* eye */}
          <ellipse cx="52.5" cy="26.5" rx="2" ry="2.7" fill="#2b1a0e" />
          <circle cx="53.2" cy="25.6" r="0.75" fill="#fff" />
          {/* cheek tuft + whiskers */}
          <path d="M35 32 l-2.5 1.5 l2.6 0.8" fill={fur} />
          <path d="M58 34.5 l8 -1.2 M58 36 l7.6 1.2" stroke="#5a3418" strokeWidth="0.7" strokeLinecap="round" opacity="0.7" />
        </g>

        <g className="cat-arm cat-arm-front">
          <path d="M45 45 q3 7 2 14" fill="none" stroke={fur} strokeWidth="5.5" strokeLinecap="round" />
          <circle cx="47" cy="59.5" r="3.1" fill={cream} />
        </g>
      </g>

      {/* near leg (in front) */}
      {leg('cat-leg cat-leg-front', 40)}
    </svg>
  );
}
