"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export default function LoginPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)

  const [signInError, setSignInError] = useState("")
  const [signUpError, setSignUpError] = useState("")

  const [signIn, setSignIn] = useState({ username: "", password: "" })
  const [signUp, setSignUp] = useState({ full_name: "", username: "", password: "" })

  async function handleSignIn(e: React.FormEvent) {
    e.preventDefault()
    setSignInError("")
    setLoading(true)
    try {
      const res = await api.login(signIn.username, signIn.password)
      if (res.success) {
        localStorage.setItem("username", res.username ?? signIn.username)
        toast.success("Welcome back!")
        router.push("/dashboard")
      } else {
        setSignInError(res.message || "Login failed")
      }
    } catch (err: any) {
      setSignInError(err.message || "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  async function handleSignUp(e: React.FormEvent) {
    e.preventDefault()
    setSignUpError("")
    setLoading(true)
    try {
      const res = await api.register(signUp.username, signUp.password, signUp.full_name)
      if (res.success) {
        localStorage.setItem("username", res.username ?? signUp.username)
        toast.success("Account created!")
        router.push("/dashboard")
      } else {
        setSignUpError(res.message || "Registration failed")
      }
    } catch (err: any) {
      setSignUpError(err.message || "Something went wrong")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-2xl bg-card p-8 shadow-lg border border-border">
        <div className="mb-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground font-bold text-xl">
            IQ
          </div>
          <h1 className="mt-4 text-2xl font-bold text-foreground">InterviewIQ</h1>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">AI-Powered Interview Assessment</p>
        </div>

        <Tabs defaultValue="signin" onValueChange={() => { setSignInError(""); setSignUpError("") }}>
          <TabsList className="mb-6 w-full">
            <TabsTrigger value="signin" className="flex-1">Sign In</TabsTrigger>
            <TabsTrigger value="signup" className="flex-1">Sign Up</TabsTrigger>
          </TabsList>

          <TabsContent value="signin">
            <form onSubmit={handleSignIn} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Username
                </label>
                <input
                  type="text"
                  required
                  value={signIn.username}
                  onChange={(e) => setSignIn({ ...signIn, username: e.target.value })}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/20"
                  placeholder="Enter your username"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={signIn.password}
                  onChange={(e) => setSignIn({ ...signIn, password: e.target.value })}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/20"
                  placeholder="Enter your password"
                />
                {signInError && (
                  <p className="text-sm text-destructive">{signInError}</p>
                )}
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? "Signing in..." : "Sign In"}
              </button>
            </form>
          </TabsContent>

          <TabsContent value="signup">
            <form onSubmit={handleSignUp} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  value={signUp.full_name}
                  onChange={(e) => setSignUp({ ...signUp, full_name: e.target.value })}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/20"
                  placeholder="Enter your full name"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Username
                </label>
                <input
                  type="text"
                  required
                  value={signUp.username}
                  onChange={(e) => setSignUp({ ...signUp, username: e.target.value })}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/20"
                  placeholder="Choose a username"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Password
                </label>
                <input
                  type="password"
                  required
                  value={signUp.password}
                  onChange={(e) => setSignUp({ ...signUp, password: e.target.value })}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-ring/20"
                  placeholder="Create a password"
                />
                {signUpError && (
                  <p className="text-sm text-destructive">{signUpError}</p>
                )}
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {loading ? "Creating account..." : "Sign Up"}
              </button>
            </form>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
