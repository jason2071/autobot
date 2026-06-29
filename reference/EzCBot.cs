using Emgu.CV;
using Emgu.CV.Structure;
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Media;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace EzCBot
{
    internal class EzCBot
    {
        public static IntPtr iHandle = Form1.iHandle;

        #region Get iHandle

        //#region var
        //public static string App;
        //public static string Class;
        //public static IntPtr iHandle;
        //#endregion var

        /* LDPlayer
         * 
                App = comboBox1.Text;
                Class = "LDPlayerMainFrame";//LDPlayer
                iHandle = EzCBot.FindWindow(Class, App); 
         */


        /* Nox
         * 
                App = comboBox1.Text;
                Class = "Qt5QWindowIcon";//Nox
                iHandle = EzCBot.FindWindow(Class, App); 
         */

        #endregion Get iHandle

        #region Class Controls Bot

        #region All Dll Import

        [DllImport("User32.dll")] public static extern IntPtr FindWindow(string strClassName, string strWindowName);
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)] public static extern int GetClassName(IntPtr hWnd, StringBuilder text, int count);
        [DllImport("user32.DLL", EntryPoint = "ReleaseCapture")] public extern static void ReleaseCapture();

        #region Dll Import

        //dll ต่างๆที่จะต้องเรียกมาใช้งาน //google
        [DllImport("User32.dll")]
        public static extern int FindWindowEx(int hwndParent, int hwndChildAfter, string strClassName, string strWindowName);
        [DllImport("User32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")]
        public static extern IntPtr SetFocus(IntPtr hwnd);
        [DllImport("user32.dll")]
        public static extern Int32 SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        public static int MakeLParam(int LoWord, int HiWord)
        {
            return (int)((HiWord << 16) | (LoWord & 0xFFFF));
        }
        [DllImport("User32.dll")]
        public static extern long SetCursorPos(int x, int y);
        [DllImport("User32.dll")]
        public static extern bool ClientToScreen(IntPtr hWnd, ref POINT point);
        [StructLayout(LayoutKind.Sequential)]
        public struct POINT
        {
            public int x;
            public int y;
        }
        [DllImport("user32.dll", CharSet = CharSet.Auto, CallingConvention = CallingConvention.StdCall)]
        public static extern void mouse_event(long dwFlags, long dx, long dy, long cButtons, long dwExtraInfo);
        private const int MOUSEEVENTF_LEFTDOWN = 0x02;
        private const int MOUSEEVENTF_LEFTUP = 0x04;
        private const int MOUSEEVENTF_RIGHTDOWN = 0x08;
        private const int MOUSEEVENTF_RIGHTUP = 0x10;
        [DllImport("user32.dll", SetLastError = true)]
        public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        [return: MarshalAs(UnmanagedType.Bool)]
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern bool PostMessage(IntPtr hWnd, uint Msg, int wParam, int lParam);
        [DllImport("user32.dll")]

        //dll ต่างๆที่จะต้องเรียกมาใช้งาน //google
        //////////////////////////////////

        public static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string lpszClass, string lpszWindow);
        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        public static extern IntPtr SendMessage(IntPtr hWnd, int Msg, int wParam, IntPtr lParam);

        #endregion Dll Import

        #endregion All Dll Import

        #region Get Color

        #region DllImport
        [DllImport("user32.dll", SetLastError = true)]
        //internal static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
        //[DllImport("user32.dll", EntryPoint = "GetDC")]
        internal extern static IntPtr GetDC(IntPtr hWnd);
        [DllImport("gdi32.dll", EntryPoint = "CreateCompatibleDC")]
        internal extern static IntPtr CreateCompatibleDC(IntPtr hdc);
        [DllImport("gdi32.dll", EntryPoint = "CreateCompatibleBitmap")]
        internal extern static IntPtr CreateCompatibleBitmap(IntPtr hdc, int nWidth, int nHeight);
        [DllImport("gdi32.dll", EntryPoint = "DeleteDC")]
        internal extern static IntPtr DeleteDC(IntPtr hDc);
        [DllImport("user32.dll", EntryPoint = "ReleaseDC")]
        internal extern static IntPtr ReleaseDC(IntPtr hWnd, IntPtr hDc);
        [DllImport("gdi32.dll", EntryPoint = "BitBlt")]
        internal extern static bool BitBlt(IntPtr hdcDest, int xDest, int yDest, int wDest, int hDest, IntPtr hdcSource, int xSrc, int ySrc, int RasterOp);
        [DllImport("gdi32.dll", EntryPoint = "SelectObject")]
        internal extern static IntPtr SelectObject(IntPtr hdc, IntPtr bmp);
        [DllImport("gdi32.dll", EntryPoint = "DeleteObject")]
        internal extern static IntPtr DeleteObject(IntPtr hDc);
        [DllImport("user32.dll")]
        //public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
        //[DllImport("user32.dll", SetLastError = true)]
        public static extern int GetWindowDC(Int32 window);
        [DllImport("gdi32.dll", SetLastError = true)]
        public static extern uint GetPixel(Int32 dc, Int32 x, Int32 y);
        [DllImport("user32.dll", SetLastError = true)]
        public static extern int ReleaseDC(Int32 window, Int32 dc);
        public static int ganx;
        public static int gany;
        //public static int WinSizeWidth;
        //public static int WinSizeHeight;
        public const int HSRCCOPY = 0x00CC0020;

        #endregion

        #region Var

        public static bool HStatus;
        public static bool CKStatus = false;
        public static string CKCOLOR = "";

        #endregion

        public static Color GetColorAt(Int32 hwnd, Int32 x, Int32 y)
        {
            ganx = x;
            gany = y;
            Int32 dc = GetWindowDC(hwnd);
            Int32 a = (int)GetPixel(dc, x, y);
            ReleaseDC(hwnd, dc);
            return Color.FromArgb(255, (a >> 0) & 0xff, (a >> 8) & 0xff, (a >> 16) & 0xff);
        }
        public static Size GetControlSize(IntPtr iHandle)
        {
            RECT pRect;
            Size cSize = new Size();
            GetWindowRect(iHandle, out pRect);
            cSize.Width = pRect.Right - pRect.Left;
            cSize.Height = pRect.Bottom - pRect.Top;
            WinSizeWidth = cSize.Width;
            WinSizeHeight = cSize.Height;
            return cSize;
        } //ดึงขนาดจอเกมส์หรือโปรแกรม 
        private static bool HexConverter(System.Drawing.Color c, int PixelColor, int Shade_Variation, IntPtr iHandle)
        {
            GetControlSize(iHandle);
            HStatus = false;
            Rectangle rect = Rectangle.FromLTRB(0, 0, WinSizeWidth, WinSizeHeight);
            var Dcolor = PixelColor.ToString();
            var PixelColor1 = Convert.ToInt32(Dcolor);
            Color Pixel_Color = Color.FromArgb(PixelColor1);
            Point Pixel_Coords = new Point(0, 0);
            IntPtr hdcSrc = GetDC(iHandle);
            IntPtr hdcDest = CreateCompatibleDC(hdcSrc);
            IntPtr hBitmap = CreateCompatibleBitmap(hdcSrc, rect.Width, rect.Height);
            IntPtr hOld = SelectObject(hdcDest, hBitmap);
            BitBlt(hdcDest, 0, 0, rect.Width, rect.Height, hdcSrc, rect.X, rect.Y, HSRCCOPY);
            SelectObject(hdcDest, hOld);
            DeleteDC(hdcDest);
            ReleaseDC(iHandle, hdcSrc);
            Bitmap bmp = Bitmap.FromHbitmap(hBitmap);
            BitmapData RegionIn_BitmapData = bmp.LockBits(new Rectangle(0, 0, bmp.Width, bmp.Height), ImageLockMode.ReadWrite, PixelFormat.Format24bppRgb);
            int[] Formatted_Color = new int[3] { Pixel_Color.B, Pixel_Color.G, Pixel_Color.R };
            unsafe
            {
                byte* row = (byte*)RegionIn_BitmapData.Scan0 + (gany * RegionIn_BitmapData.Stride);
                if (row[ganx * 3] >= (Formatted_Color[0] - Shade_Variation) & row[ganx * 3] <= (Formatted_Color[0] + Shade_Variation))//b
                {
                    if (row[(ganx * 3) + 1] >= (Formatted_Color[1] - Shade_Variation) & row[(ganx * 3) + 1] <= (Formatted_Color[1] + Shade_Variation))//g
                    {
                        if (row[(ganx * 3) + 2] >= (Formatted_Color[2] - Shade_Variation) & row[(ganx * 3) + 2] <= (Formatted_Color[2] + Shade_Variation))// R                           
                        {
                            Pixel_Coords = new Point(ganx + rect.X, gany + rect.Y);
                            HStatus = true;
                            goto end;
                        }
                    }
                }
            }
        end:
            bmp.UnlockBits(RegionIn_BitmapData);
            DeleteObject(hBitmap);
            bmp.Dispose();
            return HStatus;
        }//ได้ค่าสีจาก Getcolor  >>> และไปค้นหาสีใน ram แล้วนำไปใช้งาน //google
        private static string HexConverterOLD(System.Drawing.Color c) //HexConverter OLD
        {
            return string.Format("0x{0}", c.R.ToString("X2") + c.G.ToString("X2") + c.B.ToString("X2"));
        } //ได้ค่าสีจาก Getcolor  >>> และไปค้นหาสี แล้วนำไปใช้งาน //google
        public static bool GETCOLORFAST(IntPtr iHandle, int x, int y, int PixelColorx, int Shade_Variation) //GET COLOR OLD not use Shade_Variation
        {

            IntPtr appHandle = Form1.iHandle;
            string hexStr = string.Format("{0:x}", PixelColorx);
            hexStr = hexStr.ToUpper();


            Console.WriteLine(hexStr);


            if (hexStr.Length == 5)
            {
                hexStr = "0x0" + hexStr;
            }
            else if (hexStr.Length == 4)
            {
                hexStr = "0x00" + hexStr;
            }
            else if (hexStr.Length == 3)
            {
                hexStr = "0x000" + hexStr;
            }
            else if (hexStr.Length == 2)
            {
                hexStr = "0x0000" + hexStr;
            }
            else if (hexStr.Length == 1)
            {
                hexStr = "0x00000" + hexStr;
            }
            else
            {
                hexStr = "0x" + hexStr;
            }

            if (GETCOLORSTRING(x, y) == hexStr)
            {

                CKStatus = true;
                CKCOLOR = hexStr;
            }
            else
            {
                CKStatus = false;
                CKCOLOR = hexStr;
            }
            return CKStatus;
        }//ดึงค่าสีมาเช็คเปรียบเทียบ
        public static bool GETCOLOR(IntPtr iHandle, int x, int y, int PixelColor, int Shade_Variation)
        {
            IntPtr appHandle = iHandle;
            return HexConverter(GetColorAt(appHandle.ToInt32(), x, y), PixelColor, Shade_Variation, iHandle);
        }//รับค่าสีมาแล้วส่งไปยัง HexConverter เพิ้อไปค้นหา
        public static string GETCOLORSTRING(int x, int y)
        {
            IntPtr appHandle = Form1.iHandle;
            return HexConverterOLD(GetColorAt(appHandle.ToInt32(), x, y));
        } //รับค่าสีมาแล้วส่งไปยัง HexConverterOLD 

        #endregion

        #region Pixel Search

        public const int SRCCOPY = 0x00CC0020;
        public static int Status;
        public static bool McStatus;
        public static Point Pixel_CoordsMc;

        public static Point PixelSearch(IntPtr iHandle, int L, int Top, int R, int Bottom, int PixelColor, int Shade_Variation)
        {
            Status = 1;
            Rectangle rect = Rectangle.FromLTRB(L, Top, R, Bottom);
            Color Pixel_Color = Color.FromArgb(PixelColor);
            Point Pixel_Coords = new Point(0, 0);
            IntPtr hdcSrc = GetDC(iHandle);
            IntPtr hdcDest = CreateCompatibleDC(hdcSrc);
            IntPtr hBitmap = CreateCompatibleBitmap(hdcSrc, rect.Width, rect.Height);
            IntPtr hOld = SelectObject(hdcDest, hBitmap);
            BitBlt(hdcDest, 0, 0, rect.Width, rect.Height, hdcSrc, rect.X, rect.Y, SRCCOPY);
            SelectObject(hdcDest, hOld);
            DeleteDC(hdcDest);
            ReleaseDC(iHandle, hdcSrc);
            Bitmap bmp = Bitmap.FromHbitmap(hBitmap);
            BitmapData RegionIn_BitmapData = bmp.LockBits(new Rectangle(0, 0, bmp.Width, bmp.Height), ImageLockMode.ReadWrite, PixelFormat.Format24bppRgb);
            unsafe
            {
                byte* scan0 = (byte*)RegionIn_BitmapData.Scan0;
                int Stride = RegionIn_BitmapData.Stride;

                for (int y = 0; y < bmp.Height; y++)
                {
                    byte* row = scan0 + (y * Stride);
                    for (int x = 0; x < bmp.Width; x++)
                    {
                        if (row[x * 3] >= (Pixel_Color.B - Shade_Variation) & row[x * 3] <= (Pixel_Color.B + Shade_Variation))//b
                        {
                            if (row[(x * 3) + 1] >= (Pixel_Color.G - Shade_Variation) & row[(x * 3) + 1] <= (Pixel_Color.G + Shade_Variation))//g
                            {
                                if (row[(x * 3) + 2] >= (Pixel_Color.R - Shade_Variation) & row[(x * 3) + 2] <= (Pixel_Color.R + Shade_Variation))//r
                                {
                                    Pixel_Coords = new Point(x + rect.X, y + rect.Y);
                                    Status = 0;
                                    goto end;
                                }
                            }
                        }
                    }
                }
            }
        end:
            bmp.UnlockBits(RegionIn_BitmapData);
            DeleteObject(hBitmap);
            bmp.Dispose();
            return Pixel_Coords;
        }

        public static Tuple<bool, Point> McPixelSearch(IntPtr iHandle, int L, int Top, int PixRect, int PixelColor, int Shade_Variation)
        {
            McStatus = false;
            Rectangle rect = Rectangle.FromLTRB(L - PixRect, Top - PixRect, L + PixRect, Top + PixRect);
            Color Pixel_Color = Color.FromArgb(PixelColor);
            Point Pixel_CoordsMc = new Point(0, 0);
            IntPtr hdcSrc = GetDC(iHandle);
            IntPtr hdcDest = CreateCompatibleDC(hdcSrc);
            IntPtr hBitmap = CreateCompatibleBitmap(hdcSrc, rect.Width, rect.Height);
            IntPtr hOld = SelectObject(hdcDest, hBitmap);
            BitBlt(hdcDest, 0, 0, rect.Width, rect.Height, hdcSrc, rect.X, rect.Y, SRCCOPY);
            SelectObject(hdcDest, hOld);
            DeleteDC(hdcDest);
            ReleaseDC(iHandle, hdcSrc);
            Bitmap bmp = Bitmap.FromHbitmap(hBitmap);
            BitmapData RegionIn_BitmapData = bmp.LockBits(new Rectangle(0, 0, bmp.Width, bmp.Height), ImageLockMode.ReadWrite, PixelFormat.Format24bppRgb);
            unsafe
            {
                byte* scan0 = (byte*)RegionIn_BitmapData.Scan0;
                int Stride = RegionIn_BitmapData.Stride;

                for (int y = 0; y < bmp.Height; y++)
                {
                    byte* row = scan0 + (y * Stride);
                    for (int x = 0; x < bmp.Width; x++)
                    {
                        if (row[x * 3] >= (Pixel_Color.B - Shade_Variation) & row[x * 3] <= (Pixel_Color.B + Shade_Variation))//b
                        {
                            if (row[(x * 3) + 1] >= (Pixel_Color.G - Shade_Variation) & row[(x * 3) + 1] <= (Pixel_Color.G + Shade_Variation))//g
                            {
                                if (row[(x * 3) + 2] >= (Pixel_Color.R - Shade_Variation) & row[(x * 3) + 2] <= (Pixel_Color.R + Shade_Variation))//r
                                {
                                    McStatus = true;
                                    Pixel_CoordsMc = new Point(x + rect.X, y + rect.Y);
                                    goto end;
                                }
                            }
                        }
                    }
                }
            }
        end:
            bmp.UnlockBits(RegionIn_BitmapData);
            DeleteObject(hBitmap);
            bmp.Dispose();
            return new Tuple<bool, Point>(McStatus, Pixel_CoordsMc);
        }
       
        #endregion

        #region Images Search

        #region Dll Import

        [DllImport("User32.dll", SetLastError = true)][return: MarshalAs(UnmanagedType.Bool)] static extern bool PrintWindow(IntPtr hWnd, IntPtr hDc, uint nFlags);
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr handle, ref Rectangle rect);

        #endregion

        public static string CaptureWindow(IntPtr handle, string path = null, string name = null)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                path = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) + "\\Capture\\";
            }

            if (string.IsNullOrWhiteSpace(name))
            {
                name = DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss") + ".png";
            }

            if (!name.EndsWith(".png"))
            {
                name += ".png";
            }


            // Get the size of the window to capture
            Rectangle rect = new Rectangle(305, 572, 845, 889);
            GetWindowRect(handle, ref rect);

            // GetWindowRect returns Top/Left and Bottom/Right, so fix it
            rect.Width -= rect.X;
            rect.Height -= rect.Y;


            // Create a bitmap to draw the capture into
            using (var bitmap = new Bitmap(rect.Width, rect.Height))

            {
                // Use PrintWindow to draw the window into our bitmap
                using (var g = Graphics.FromImage(bitmap))
                {
                    var hdc = g.GetHdc();
                    if (!PrintWindow(handle, hdc, 0))
                    {
                        var error = Marshal.GetLastWin32Error();
                        var exception = new System.ComponentModel.Win32Exception(error);
                        //Debug.WriteLine("ERROR: " + error + ": " + exception.Message);
                        return "ERROR: " + error + ": " + exception.Message;
                        // TODO: Throw the exception?
                    }
                    g.ReleaseHdc(hdc);
                }

                if (!Directory.Exists(path))
                {
                    Directory.CreateDirectory(path);
                }

                DateTime date1 = new DateTime(2015, 12, 25);

                bitmap.Save($"{path}{name}");
                Debug.WriteLine($@"Capture Window path: {path}{name} {date1.ToString()}");
            }
            return $"{path}{name}";
        }//แคปภาพหน้าจอ

        public static Point Search(IntPtr iHandle, string imgTargetPath, int sleep = 500, string path = null, string name = null, double accuracy = 0.9, bool isTest = false, string nameTest = null)
        {
            Sleep2(sleep);
            if (string.IsNullOrWhiteSpace(name))
            {
                name = "capture.png";
            }

            if (!File.Exists(imgTargetPath))
            {
                return ErrorType.Error100;
            }

            var imgSource = CaptureWindow(iHandle, path, name);
            var imgSearch = imgTargetPath;

            var source = new Image<Bgr, byte>(imgSource); // Image B
            var template = new Image<Bgr, byte>(imgSearch); // Image A
            var imageToShow = source.Copy();

            using (var result = source.MatchTemplate(template, Emgu.CV.CvEnum.TemplateMatchingType.CcoeffNormed))
            {
                result.MinMax(out _, out var maxValues, out _, out var maxLocations);
                //isTest = true;
                if (isTest)
                {
                    Console.WriteLine("Test");
                    if (string.IsNullOrWhiteSpace(nameTest))
                    {
                        nameTest = DateTime.Now.ToString("yyyy-MM-dd-HH-mm-ss") + ".png";
                    }
                    if (!nameTest.EndsWith(".png"))
                    {
                        nameTest += ".png";
                    }
                    // This is a match. Do something with it, for example draw a rectangle around it.
                    var match = new Rectangle(maxLocations[0], template.Size);
                    imageToShow.Draw(match, new Bgr(Color.Red), 3);

                    // Show imageToShow in an ImageBox (here assumed to be called imageBox1)


                    var pathTest = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) + "\\Test\\";

                    if (!Directory.Exists(pathTest))
                    {
                        Directory.CreateDirectory(pathTest);
                    }

                    imageToShow.Save(pathTest + nameTest);
                }

                // accuracy: You can try different values of the threshold. I guess somewhere between 0.75 and 0.95 would be good.
                if (maxValues[0] > accuracy)
                {

                    ErrorType.isok = true;

                    //result.X = minLocations[0].X+template.Size.
                    return maxLocations[0];
                }
                ErrorType.isok = false;
                return ErrorType.Error101;
                //throw new ApplicationException("Not found!");
            }
        }

        public static void Sleep2(int slp)
        {
            Thread.Sleep(slp);
        }
        private static void Sleep(int sleep)
        {
            throw new NotImplementedException();
        }

        public class ErrorType
        {
            public static bool isok;
            public static Point Error100 = new Point(-1, -1); // Not found image target path!
            public static Point Error101 = new Point(-1, -1); // Not found image in target!
        }

        #endregion

        #region Utility

        #region var

        public static string DateNow = DateTime.Now.ToString();

        [DllImport("user32.dll", SetLastError = true)]
        private static extern bool ShowWindow(IntPtr hwnd, int nCmdShow);

        public const int WM_COMMAND = 0x111;
        public const int WM_MOUSEMOVE = 0x0200;
        public const int WM_LBUTTONDOWN = 0x201;
        public const int WM_LBUTTONUP = 0x202;
        public const int WM_LBUTTONDBLCLK = 0x203;
        public const int WM_RBUTTONDOWN = 0x204;
        public const int WM_RBUTTONUP = 0x205;
        public const int WM_RBUTTONDBLCLK = 0x206;
        public const int WM_KEYDOWN = 0x100;
        public const int WM_KEYUP = 0x101;
        public const int WM_MOUSEWHEEL = 0x020A;
        public const int WM_MOUSEHWHEEL = 0x020E;
        public static int WinSizeWidth;
        public static int WinSizeHeight;
        private const int SW_HIDE = 0;
        private const int SW_SHOW = 1;
        //เป็นค่า hex ไว้ตั่งค่า ตอนนี้ยังไม่ได้ใช้
        

        [StructLayout(LayoutKind.Sequential)]
        public struct RECT
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        #endregion var

        public static void loadProcessList(ComboBox cm,string name)//โหลดรายชื่อแอพจำลอง
        {
            cm.Items.Clear();

            var MyProcess = Process.GetProcessesByName(name);
            //dnplayer
            //Nox
            //HD-Player

            try
            {
                foreach (var process1 in MyProcess)
                {
                    if (!string.IsNullOrEmpty(process1.MainWindowTitle))
                    {
                        cm.Items.Add(process1.MainWindowTitle);

                    }
                }
            }
            catch (Exception exc) { MessageBox.Show(exc.Message); }
        }

        public static void Clicktobg(IntPtr iHandle, int x, int y, int clickcount = 1) //click bg
        {
            SendMessage(iHandle, WM_LBUTTONDOWN, 0x00000001, MakeLParam(x, y));
            SendMessage(iHandle, WM_LBUTTONUP, 0x00000000, MakeLParam(x, y));
        }//คลิกโดยที่ไม่ขยับเมาส์

        public static void LDClickBG(int x, int y)
        {
            IntPtr hWnd = FindWindow(null, Form1.App);
            IntPtr Childs = FindWindowEx(hWnd, IntPtr.Zero, "RenderWindow", "TheRender");
            IntPtr MakeLParam = new IntPtr(x | (y << 16));
            SendMessage(Childs, WM_LBUTTONDOWN, 1, MakeLParam);
            SendMessage(Childs, WM_LBUTTONUP, 0, MakeLParam);
        }//คลิกโดยที่ไม่ขยับเมาส์ LD Player

        public static void BSClickBG(IntPtr iHandle, int x, int y, int clickcount = 1)
        {/*
          * BlueStacks 5.6++
          * var first = FindWindow("Qt5154QWindowOwnDCIcon", app);
            AppName = FindWindowEx(first, IntPtr.Zero, "Qt5154QWindowIcon", "HD-Player");
            */
            SendMessage(iHandle, WM_LBUTTONDOWN, 0x00000001, MakeLParam(x, y));
            PostMessage(iHandle, (uint)WM_LBUTTONDOWN, 0x00000001, MakeLParam(x, y));
            SendMessage(iHandle, WM_LBUTTONUP, 0x00000000, MakeLParam(x, y));
            PostMessage(iHandle, (uint)WM_LBUTTONUP, 0x00000000, MakeLParam(x, y));

            //Bluestacks y-35 นะครับถึงจะคลิกตรงจุด
        }//คลิกโดยที่ไม่ขยับเมาส์ Bluestacks 5.6++
        
        public static void ClickDragBG(IntPtr iHandle, int Xstart, int Ystart, int XEnd, int YEnd, int Delay) //STARTPOINT X,Y TO END POINT X,Y
        {
            SendMessage(iHandle, WM_LBUTTONDOWN, 0x00000001, MakeLParam(XEnd, YEnd));
            sleep(Delay);
            SendMessage(iHandle, WM_MOUSEMOVE, 0x00000001, MakeLParam(Xstart, Ystart));
            sleep(Delay);
            SendMessage(iHandle, WM_MOUSEMOVE, 0x00000001, MakeLParam(Xstart, Ystart));
            sleep(Delay);
            SendMessage(iHandle, WM_LBUTTONUP, 0x00000001, MakeLParam(XEnd, YEnd));
            SendMessage(iHandle, WM_LBUTTONUP, 0x00000001, MakeLParam(XEnd, YEnd));

        }//คลิกลากเมาส์จากตำแหน่ง แรก ไปยังตำแหน่ง สุดท้ายที่ต้องการ ไม่ขยับเมาส์
        
        public static void LDClickDragBG(int Xstart, int Ystart, int XEnd, int YEnd, int Delay) //STARTPOINT X,Y TO END POINT X,Y
        {
            IntPtr hWnd = FindWindow(null, Form1.App);
            IntPtr Childs = FindWindowEx(hWnd, IntPtr.Zero, "RenderWindow", "TheRender");
            IntPtr makeLParam = new IntPtr(Xstart | (Ystart << 16));
            IntPtr makeLParam2 = new IntPtr(XEnd | (YEnd << 16));

            SendMessage(Childs, WM_LBUTTONDOWN, 0x00000001, makeLParam);
            //sleep(Delay);
            //SendMessage(Childs, WM_MOUSEMOVE, 0x00000001, makeLParam2);
            sleep(500);
            SendMessage(Childs, WM_MOUSEMOVE, 0x00000001, makeLParam2);
            sleep(Delay);
            SendMessage(Childs, WM_LBUTTONUP, 0x00000001, makeLParam);
            SendMessage(Childs, WM_LBUTTONUP, 0x00000001, makeLParam);

        }//คลิกลากเมาส์จากตำแหน่ง แรก ไปยังตำแหน่ง สุดท้ายที่ต้องการ ไม่ขยับเมาส์

        public static void MouseClick(IntPtr iHandle, int Gx, int Gy, string TypeClick = "LEFT")/// mousemove in program no sceen
        {
            POINT p = new POINT();
            p.x = Convert.ToInt16(Gx);
            p.y = Convert.ToInt16(Gy);
            EzCBot.ClientToScreen(iHandle, ref p);
            EzCBot.SetCursorPos(p.x, p.y);
            if (TypeClick == "LEFT")
            {
                mouse_event(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP, p.x, p.y, 0, 0);
            }
            else if (TypeClick == "RIGHT")
            {
                mouse_event(MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_RIGHTUP, p.x, p.y, 0, 0);
            }
        }//คลิกเเมาส์

        public static void MouseMove(IntPtr iHandle, int x, int y) /// mousemove in program no sceen
        {
            POINT p = new POINT();
            p.x = Convert.ToInt16(x);
            p.y = Convert.ToInt16(y);
            EzCBot.ClientToScreen(iHandle, ref p);
            EzCBot.SetCursorPos(p.x, p.y);
        }//ย้ายเมาส์

        public static void ActiveWindow(IntPtr iHandle) //setactivate
        {
            IntPtr h = iHandle;
            ShowWindow(h, SW_SHOW);
            SetForegroundWindow(h);
            SetFocus(h);
        }//แอคทืฟโปรแกรม

        public static void HideApp(IntPtr iHandle)
        {
            IntPtr h = iHandle;
            ShowWindow(h, SW_HIDE);
        }//ซ้อนโปรแกรม

        public static void ShowAPP(IntPtr iHandle)
        {
            IntPtr h = iHandle;
            ShowWindow(h, SW_SHOW);
        }//แสดงโปรแกรม

        public static void WindowMove(IntPtr iHandle, int x, int y)
        {
            GetControlSize(iHandle);
            MoveWindow(iHandle, x, y, WinSizeWidth, WinSizeHeight, true);
        }//ย้ายหน้าต่างไปยังตำแหน่งต่างๆ

        public static bool CheckProcess(string processname)
        {
            bool StatusCheck = false;
            Process[] p = Process.GetProcessesByName(processname);
            if (p.Length > 0)
            {
                StatusCheck = true;
            }
            return StatusCheck;
        } //เช็คโปรแแกรมว่าเปิดอยุ่หรือป่าว

        public static void sleep(int slp)
        {
            Thread.Sleep(slp);
        }//พักโปรแกรมหรือเรียกว่า สลิปป

        public static void saveLogFile(string detail)
        {
            using (StreamWriter writer = new StreamWriter(Application.StartupPath + "/log.txt", true))
            {
                writer.WriteLine(DateTime.Now + " " + detail);
            }
        }//บันทึกไฟล์ Log เพื่อเก็บข้อมูล

        public static void RichTextBoxShow(RichTextBox rt, string text)
        {
            rt.Invoke(new Action(() => rt.AppendText(Environment.NewLine + $"{DateNow} : \"{text}\"")));
            rt.Invoke(new Action(() => rt.ScrollToCaret()));
        }// สร้างข้อความไปโชว์ใน RichTextBox

        //Function to get random number
        private static readonly Random getrandom = new Random();
        public static int RandomNumberX(int min, int max)
        {
            lock (getrandom) // synchronize
            {
                return getrandom.Next(min, max);
            }
        }//สุ่มตัวเลข
        public static int RandomNumberY(int min, int max)
        {
            lock (getrandom) // synchronize
            {
                return getrandom.Next(min, max);
            }
        }//สุ่มตัวเลข
        public static int RandomNumber(int min, int max)
        {
            lock (getrandom) // synchronize
            {
                return getrandom.Next(min, max);
            }
        }//สุ่มตัวเลข
        //private readonly Random _random = new Random();
        public static string RandomString(int size, bool lowerCase = false)
        {
            var builder = new StringBuilder(size);

            // Unicode/ASCII Letters are divided into two blocks
            // (Letters 65–90 / 97–122):   
            // The first group containing the uppercase letters and
            // the second group containing the lowercase.  

            // char is a single Unicode character  
            char offset = lowerCase ? 'a' : 'A';
            const int lettersOffset = 26; // A...Z or a..z: length = 26  

            for (var i = 0; i < size; i++)
            {
                var @char = (char)getrandom.Next(offset, offset + lettersOffset);
                builder.Append(@char);
            }

            return lowerCase ? builder.ToString().ToLower() : builder.ToString();
        }//สุ่มตัวอักษร A-Z ( false = อักษรใหญ่เท่านั้น, true = ทั้งอักษรใหญ่และเล็ก ) 
                
        #region notification  การแจ้งเตือน
        public static void popup()
        {
            SoundPlayer player = new SoundPlayer();
            player.SoundLocation = @"C:\Windows\Media\Alarm01.wav";
            player.Play();
            sleep(1000);
        }//แจ้งเตือนด้วยเสียง

        public static void SendLine(string token, string txtmsg)
        {
            //string token = linetoken;
            string url = "https://notify-api.line.me/api/notify";
            using (var client = new HttpClient())
            {
                client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
                using (var line = new MultipartFormDataContent())
                {
                    line.Add(new StringContent(txtmsg), "message");
                    var response = client.PostAsync(url, line).Result;
                    var content = response.Content.ReadAsStringAsync().Result;
                }
            }
        }//ส่งข้อความ เข้า Line Notify

        public static byte[] imagepath;
        public static void SendLineAndPic(string token, string txtmsg, byte[] image = null)
        {
            //string token = linetoken.ToString();
            string url = "https://notify-api.line.me/api/notify";
            using (var client = new HttpClient())
            {
                client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
                using (var line = new MultipartFormDataContent())
                {
                    line.Add(new StringContent(txtmsg), "message");
                    line.Add(new ByteArrayContent(image), "imageFile", "test.png");

                    var response = client.PostAsync(url, line).Result;
                    var content = response.Content.ReadAsStringAsync().Result;
                }
            }
        }//ส่งข้อความและรูปภาพ เข้า Line Notify 

        public static void SendLineNotify(string LineToken, string txtmsg, string path = null)
        {
            if (string.IsNullOrWhiteSpace(path))
            {
                path = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location) + "\\Capture\\";
            }
            CaptureWindow(Form1.iHandle, path, "SendLine.png");
            sleep(1000);
            var pic = File.ReadAllBytes(path + "SendLine.png");
            SendLineAndPic(LineToken, txtmsg, pic);
        }//แคปภาพ แล้วส่ง Line

        #endregion notification   การแจ้งเตือน

        #endregion Utility

        #endregion Class Controls Bot
    }
}
