import * as React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

type CarouselContextValue = {
  viewportRef: React.MutableRefObject<HTMLDivElement | null>
}

const CarouselContext = React.createContext<CarouselContextValue | null>(null)

function useCarouselContext(component: string): CarouselContextValue {
  const ctx = React.useContext(CarouselContext)
  if (!ctx) {
    throw new Error(`${component} must be used within <Carousel> and <CarouselContent> context`)
  }
  return ctx
}

const Carousel: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({ className, children, ...props }) => {
  const viewportRef = React.useRef<HTMLDivElement | null>(null)
  return (
    <CarouselContext.Provider value={{ viewportRef }}>
      <div className={cn('relative', className)} {...props}>
        {children}
      </div>
    </CarouselContext.Provider>
  )
}

const CarouselContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => {
    const { viewportRef } = useCarouselContext('CarouselContent')

    const setRefs = React.useCallback(
      (node: HTMLDivElement | null) => {
        viewportRef.current = node
        if (!ref) return
        if (typeof ref === 'function') {
          ref(node)
        } else {
          ref.current = node
        }
      },
      [ref, viewportRef],
    )

    return (
      <div
        ref={setRefs}
        className={cn(
          'flex gap-4 overflow-x-auto scroll-smooth rounded-2xl border border-border/50 bg-muted/10 p-4',
          className,
        )}
        {...props}
      >
        {children}
      </div>
    )
  },
)
CarouselContent.displayName = 'CarouselContent'

const CarouselItem = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('min-w-[16rem] shrink-0 grow-0 scroll-m-2', className)}
      {...props}
    />
  ),
)
CarouselItem.displayName = 'CarouselItem'

function CarouselControl({ direction, className }: { direction: 'prev' | 'next'; className?: string }) {
  const { viewportRef } = useCarouselContext(direction === 'prev' ? 'CarouselPrevious' : 'CarouselNext')

  const handleClick = () => {
    const node = viewportRef.current
    if (!node) return
    const delta = node.clientWidth * 0.85
    node.scrollBy({ left: direction === 'next' ? delta : -delta, behavior: 'smooth' })
  }

  return (
    <Button
      type="button"
      variant="secondary"
      size="icon"
      className={cn(
        'absolute top-1/2 z-10 hidden -translate-y-1/2 rounded-full shadow-lg lg:flex',
        direction === 'prev' ? 'left-3' : 'right-3',
        className,
      )}
      onClick={handleClick}
    >
      {direction === 'prev' ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
    </Button>
  )
}

const CarouselPrevious = ({ className }: { className?: string }) => (
  <CarouselControl direction="prev" className={className} />
)

const CarouselNext = ({ className }: { className?: string }) => (
  <CarouselControl direction="next" className={className} />
)

export { Carousel, CarouselContent, CarouselItem, CarouselNext, CarouselPrevious }
