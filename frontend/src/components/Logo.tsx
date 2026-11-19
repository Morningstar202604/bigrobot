/**
 * 品牌标识：B3 十字总线 + 中心环（assets 已安装到 public/）。
 *
 * 旧版是朱印「知」的手绘 SVG，随 BigRobot 改名一并作废；这里保留组件外壳，
 * 让 ResponsiveShell / VisitorChat 的调用点不必改动，只把内部换成正式品牌资产。
 * 深色侧栏用单色白版，浅色用主标。
 */
import { memo } from 'react'

interface LogoProps {
  size?: number
  onDark?: boolean
  withText?: boolean
  subtitle?: string
  name?: string
}

export const Logo = memo(function Logo({
  size = 32,
  onDark = false,
  withText = false,
  subtitle,
  name = 'BigRobot',
}: LogoProps) {
  const src = onDark ? '/logo-mono-white.svg' : '/logo.svg'
  const textColor = onDark ? '#F2EFE9' : 'inherit'
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: size * 0.3 }}>
      <img
        src={src}
        width={size}
        height={size}
        alt="BigRobot"
        style={{ flexShrink: 0, borderRadius: size * 0.22 }}
      />
      {withText && (
        <span style={{ display: 'inline-flex', flexDirection: 'column', lineHeight: 1.2, color: textColor }}>
          <span style={{ fontSize: Math.max(12, size * 0.46), fontWeight: 600 }}>{name}</span>
          {subtitle && (
            <span style={{ fontSize: Math.max(10, size * 0.3), opacity: 0.65 }}>{subtitle}</span>
          )}
        </span>
      )}
    </span>
  )
})

export default Logo
